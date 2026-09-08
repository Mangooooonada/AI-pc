"""Self-update for Jarvis: release feed + asset downloads against GitHub.

Jarvis ships from GitHub Releases (see scripts/release.py).  This module is
the engine behind the in-app updater (Settings → Updates) and it works on
BOTH public and private repositories:

  * No token configured   → anonymous calls (fine while the repo is public).
  * ``JARVIS_UPDATE_TOKEN`` set → every feed/asset call authenticates with it,
    so releases keep working after the repo goes private.  A fine-grained
    GitHub PAT with "Contents: read" on the repo is enough.

Nothing here talks to the network at import time, and every function is
parameterised (repo / api_base / token) so tests can point it at a local
fake GitHub instead of the real internet (see tests/update_sim.py).

    from jarvis.updater import check_for_update, download_release, install_update

    info = check_for_update()          # {"ok": True, "update_available": ...}
    if info.get("ok") and info["update_available"]:
        zip_path = download_release(info["release"], tmp)
        install_update(zip_path)        # swaps code, keeps .env / data
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from .config import ROOT  # importing config also loads .env, so the token is seen

DEFAULT_REPO = "Mangooooonada/AI-pc"
DEFAULT_API = "https://api.github.com"
# GitHub's Releases API works for the *latest* release; tags' auto source
# zips keep every old version downloadable forever.
ASSET_PREFIX = "JARVIS-v"


class UpdateError(Exception):
    """Raised for updater failures; ``kind`` is one of
    offline | auth | empty | http | corrupt | unsafe."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


# ---------------------------------------------------------------- helpers --
def auth_token(explicit: Optional[str] = None) -> str:
    """The GitHub token used for authenticated feed/asset calls.

    Resolution order: explicit argument → ``JARVIS_UPDATE_TOKEN`` env (which
    may come from .env, loaded by config) → anonymous ("").
    """
    tok = explicit if explicit is not None else os.getenv("JARVIS_UPDATE_TOKEN", "")
    return str(tok).strip()


def _repo(repo: Optional[str]) -> str:
    return (repo or os.getenv("JARVIS_UPDATE_REPO") or DEFAULT_REPO).strip().strip("/")


def _api_base(api_base: Optional[str]) -> str:
    return (api_base or os.getenv("JARVIS_UPDATE_API") or DEFAULT_API).rstrip("/")


def _web_base(api_base: Optional[str]) -> str:
    """Turn an API base into the matching website base (for archive URLs).

    Only github.com is special-cased: https://api.github.com → https://github.com.
    Any other base (tests, GH Enterprise) is used as-is.
    """
    base = _api_base(api_base)
    if base == "https://api.github.com":
        return "https://github.com"
    return base


def _ca_bundle() -> Any:
    """Where to get CA certs from.

    Order:
      1. JARVIS_UPDATE_CA_BUNDLE env (explicit file/dir, or 'false'/'0' → no verify)
      2. certifi.where() if certifi is installed
      3. True (requests' default bundle)
    """
    raw = (os.getenv("JARVIS_UPDATE_CA_BUNDLE") or "").strip()
    if raw:
        low = raw.lower()
        if low in {"0", "false", "no", "off", "insecure"}:
            return False
        p = Path(raw).expanduser()
        if p.exists():
            return str(p)
        # If the env points to a non-existent path, fall through to certifi
    try:
        import certifi  # type: ignore

        where = certifi.where()
        if Path(where).exists():
            return where
    except Exception:
        pass
    return True


def _session(token: str, verify: Any = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jarvis-updater",
        }
    )
    if token:
        # Requests strips Authorization automatically when a redirect leaves
        # the host that got the header — exactly what asset redirects need.
        s.headers["Authorization"] = f"Bearer {token}"
    s.verify = _ca_bundle() if verify is None else verify
    return s


def _get_with_fallback(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    headers: Optional[Dict[str, str]] = None,
    stream: bool = False,
) -> requests.Response:
    """GET with CA-bundle fallback.

    Corporate proxies / outdated Windows cert stores often break verification
    for api.github.com. We try the normal bundle first; on SSLError we retry
    once with the alternate bundle (certifi ↔ system) and finally, if
    JARVIS_UPDATE_CA_BUNDLE is not explicitly set to a path, with verify=False
    as a last resort so the updater can still explain the failure mode instead
    of crashing with an opaque SSL error.

    Returns the Response on success; raises RequestException/SSLError on
    failure so callers can turn it into UpdateError.
    """
    # First attempt: whatever _ca_bundle() resolved to
    try:
        return session.get(url, timeout=timeout, headers=headers, stream=stream)
    except requests.exceptions.SSLError as first_exc:
        # Second attempt: try the other bundle (certifi vs system)
        try:
            import certifi  # type: ignore

            alt = certifi.where()
            if session.verify != alt and Path(alt).exists():
                session.verify = alt
                return session.get(url, timeout=timeout, headers=headers, stream=stream)
        except Exception:
            pass
        # Third attempt: system default (True) if we were on certifi
        try:
            if session.verify is not True:
                session.verify = True
                return session.get(url, timeout=timeout, headers=headers, stream=stream)
        except requests.exceptions.SSLError:
            pass
        # Last resort: if user didn't pin a CA bundle, try insecure once so
        # we can at least reach GitHub and tell them what's wrong. This is
        # gated — if JARVIS_UPDATE_CA_BUNDLE is set, we respect it and don't
        # silently downgrade.
        if not (os.getenv("JARVIS_UPDATE_CA_BUNDLE") or "").strip():
            try:
                session.verify = False
                # Suppress only the InsecureRequestWarning for this one call
                import warnings

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return session.get(url, timeout=timeout, headers=headers, stream=stream)
            except Exception:
                pass
        raise first_exc


def parse_version(raw: Any) -> Tuple[int, ...]:
    """'v1.2.9' / '1.2.9' → (1, 2, 9).  Non-numeric bits are dropped."""
    text = str(raw or "").strip().lstrip("vV").replace("-", ".")
    nums = []
    for part in text.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            nums.append(int(digits))
        else:
            break
    return tuple(nums) or (0,)


def current_version() -> str:
    try:
        import jarvis

        return str(jarvis.__version__ or "0.0.0-dev").strip()
    except Exception:  # noqa: BLE001 - never let version detection crash an update
        return "0.0.0-dev"


def _friendly(error: UpdateError, token: str) -> str:
    if error.kind == "auth":
        hint = (
            ""
            if token
            else " — if the repo is private, set JARVIS_UPDATE_TOKEN (a GitHub PAT with Contents: read) in .env"
        )
        return error.message + hint
    return error.message


# ------------------------------------------------------------------ feed --
def fetch_release(
    repo: Optional[str] = None,
    api_base: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[Dict[str, Any], str]:
    """Fetch the latest release feed entry.

    Returns ``(release_json, token_used)`` on success (HTTP 200).  Raises
    :class:`UpdateError` with a helpful message for offline/auth/empty/HTTP
    failures so callers never have to decode status codes themselves.
    """
    repo = _repo(repo)
    base = _api_base(api_base)
    token = auth_token(token)
    url = f"{base}/repos/{repo}/releases/latest"
    try:
        r = _get_with_fallback(_session(token), url, timeout=timeout)
    except requests.RequestException as exc:
        raise UpdateError("offline", f"could not reach the release feed: {exc.__class__.__name__}") from exc
    if r.status_code == 200:
        return r.json(), token
    if r.status_code in (401, 403):
        raise UpdateError(
            "auth",
            "the release feed refused access"
            + ("" if token else " (the repo is probably private)"),
        )
    if r.status_code == 404:
        raise UpdateError(
            "empty",
            "no public release feed found"
            + ("" if token else " — private repos need JARVIS_UPDATE_TOKEN"),
        )
    raise UpdateError("http", f"the release feed answered HTTP {r.status_code}")


def pick_asset(release: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Choose the release asset Jarvis should download.

    Preference: the ``JARVIS-v<version>.zip`` bundle that scripts/release.py
    uploads; otherwise any ``*.zip`` asset; otherwise ``None`` meaning "no
    uploaded asset — fall back to the tag's source zip (archive)".
    """
    want = f"{ASSET_PREFIX}{version.lstrip('v')}.zip"
    assets = release.get("assets") or []
    zips = sorted(
        (a for a in assets if (a.get("name") or "").lower().endswith(".zip")),
        key=lambda a: a.get("name", ""),
    )
    for a in zips:
        if a.get("name") == want:
            return dict(a, _kind="asset")
    if zips:
        return dict(zips[0], _kind="asset")
    return {}


def check_for_update(
    repo: Optional[str] = None,
    api_base: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """One-call update check.  Never raises — always returns a JSON-able dict.

    Result fields: ok, error (when ok is False), offline, authenticated,
    current_version, latest_version, update_available, repo, release
    (feed entry, when ok), asset (chosen asset dict or {}).
    """
    repo = _repo(repo)
    base = _api_base(api_base)
    token = auth_token(token)
    cur = current_version()
    try:
        release, used = fetch_release(repo=repo, api_base=base, token=token, timeout=timeout)
    except UpdateError as exc:
        return {
            "ok": False,
            "error": _friendly(exc, token),
            "kind": exc.kind,
            "offline": exc.kind == "offline",
            "authenticated": bool(token),
            "repo": repo,
            "current_version": cur,
        }
    tag = str(release.get("tag_name") or release.get("name") or "")
    latest = tag.lstrip("vV")
    info: Dict[str, Any] = {
        "ok": True,
        "authenticated": bool(used),
        "repo": repo,
        "current_version": cur,
        "latest_version": latest,
        "update_available": parse_version(latest) > parse_version(cur),
        "release": release,
        "asset": pick_asset(release, latest),
    }
    rel = release.get("html_url") or f"{_web_base(base)}/{repo}/releases/tag/{tag}"
    info["release_url"] = rel
    return info


# --------------------------------------------------------------- download --
def _asset_api_url(api_base: str, repo: str, asset_id: Any) -> str:
    return f"{api_base}/repos/{repo}/releases/assets/{asset_id}"


def download_release(
    release: Dict[str, Any],
    dest_dir: Any,
    repo: Optional[str] = None,
    api_base: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 30.0,
) -> Path:
    """Download the release bundle (uploaded asset, or the tag's source zip).

    * token set      → every request authenticates; the upload is pulled via
      the API asset endpoint (``Accept: application/octet-stream``), which is
      the only path that works for private repos.
    * no token       → public repo: ``browser_download_url`` is used directly.

    Returns the path of the saved file inside ``dest_dir`` (created if
    missing).  Raises :class:`UpdateError` on transport, HTTP, or corrupt-zip
    failures.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    repo = _repo(repo)
    base = _api_base(api_base)
    token = auth_token(token)
    version = str(release.get("tag_name") or "").lstrip("vV") or "latest"

    asset = pick_asset(release, version)
    session = _session(token)
    if asset.get("id"):
        # The API asset endpoint (Accept: application/octet-stream) is the
        # reliable path for BOTH cases: anonymous works on public repos, and
        # with a token it is exactly how private-repo assets must be pulled.
        url = _asset_api_url(base, repo, asset["id"])
        headers = {"Accept": "application/octet-stream"}
        name = asset.get("name") or f"{ASSET_PREFIX}{version}.zip"
        try:
            r = _get_with_fallback(session, url, timeout=timeout, headers=headers, stream=True)
        except requests.RequestException as exc:
            raise UpdateError("offline", f"asset download failed: {exc.__class__.__name__}") from exc
    else:
        # No uploaded asset → the tag's source zip (GitHub auto-generates it).
        # With a token, route through the API zipball (private-safe); without,
        # hit the public archive URL straight.  Both want the full tag, v and
        # all (GitHub's refs are named v1.2.9).
        tag = str(release.get("tag_name") or "").strip() or f"v{version}"
        if token:
            url = f"{base}/repos/{repo}/zipball/{tag}"
        else:
            url = f"{_web_base(base)}/{repo}/archive/refs/tags/{tag}.zip"
        name = f"{ASSET_PREFIX}{version}.zip"
        try:
            r = _get_with_fallback(session, url, timeout=timeout, stream=True)
        except requests.RequestException as exc:
            raise UpdateError("offline", f"archive download failed: {exc.__class__.__name__}") from exc
    if r.status_code != 200:
        raise UpdateError(
            "http",
            f"download answered HTTP {r.status_code}"
            + ("" if token else " — a private repo needs JARVIS_UPDATE_TOKEN"),
        )
    safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in name) or "jarvis.zip"
    out = dest / safe
    size = 0
    try:
        with out.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
                    size += len(chunk)
    except OSError as exc:
        out.unlink(missing_ok=True)
        raise UpdateError("offline", f"could not write download: {exc}") from exc
    if size == 0 or not zipfile.is_zipfile(out):
        out.unlink(missing_ok=True)
        raise UpdateError("corrupt", "downloaded bundle is empty or not a valid zip")
    return out


# ---------------------------------------------------------------- install --
def _extract_safe(zip_path: Path, stage: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            raw = info.filename
            p = Path(raw)
            if not p.parts or ".." in p.parts or p.is_absolute():
                raise UpdateError("corrupt", f"unsafe path inside bundle: {raw!r}")
            # Reject symlink entries outright: extraction never follows links,
            # so a crafted bundle cannot smuggle files outside the stage dir.
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise UpdateError("corrupt", f"symlink inside bundle refused: {raw!r}")
        zf.extractall(stage)


def install_update(
    zip_path: Any,
    target_dir: Optional[Any] = None,
    keep_backup: bool = True,
) -> Dict[str, Any]:
    """Install a downloaded release bundle over the app code.

    Only the top-level entries the bundle actually contains are replaced
    (the archive is a ``git archive`` of the repo, so that is the code);
    everything else under the target — ``.env``, user data, other folders —
    is left alone.  A timestamped backup of the replaced entries is kept
    next to the target unless ``keep_backup=False``.

    Refuses loudly when the target looks like a git working tree (dev
    checkouts update via git, not by overwriting files) or when the bundle
    is missing the app skeleton.
    """
    zpath = Path(zip_path)
    target = Path(target_dir) if target_dir is not None else ROOT
    if not zipfile.is_zipfile(zpath):
        raise UpdateError("corrupt", f"{zpath.name} is not a valid zip")
    if (target / ".git").exists():
        raise UpdateError(
            "unsafe",
            "this is a git checkout — pull the new version instead of installing over it",
        )
    target.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix="jarvis-update-"))
    try:
        _extract_safe(zpath, stage)

        # A release archive may nest everything under one folder (git archive
        # with --prefix, e.g. JARVIS-v1.2.9/).  Unwrap a single top-level
        # folder so the entries to replace are the real repo top level.
        entries = [p for p in stage.iterdir() if p.name != "_unwrapped"]
        if (
            len(entries) == 1
            and entries[0].is_dir()
            and not (stage / "main.py").exists()
        ):
            inner = entries[0]
            for child in list(inner.iterdir()):
                shutil.move(str(child), str(stage / child.name))
            inner.rmdir()

        # The bundle must look like Jarvis before we touch anything.
        if not (stage / "main.py").exists() or not (stage / "jarvis").is_dir():
            raise UpdateError(
                "corrupt",
                "bundle does not look like a Jarvis release (no main.py / jarvis/)",
            )

        members = sorted(p.name for p in stage.iterdir())
        replaced, backup_dir = [], None
        if keep_backup:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = target.parent / f"{target.name}.backup-{stamp}"
            backup_dir.mkdir(exist_ok=True)
        for name in members:
            src = stage / name
            dst = target / name
            if dst.exists() and keep_backup:
                bak = backup_dir / name  # type: ignore[operator]
                bak.parent.mkdir(parents=True, exist_ok=True)
                if bak.exists():
                    shutil.rmtree(bak) if bak.is_dir() else bak.unlink()
                shutil.move(str(dst), str(bak))
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            replaced.append(name)
        return {
            "ok": True,
            "installed": sorted(replaced),
            "backup": str(backup_dir) if keep_backup else None,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)
