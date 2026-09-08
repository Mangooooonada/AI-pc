#!/usr/bin/env python3
"""Update simulation: release feed + asset downloads against a FAKE GitHub.

There is no real GitHub and no guarantee the repo stays public, so this runs
the REAL updater code (jarvis.updater) against a faithful local stand-in for
the GitHub Releases API:

  * public repo   → anonymous feed + asset download must work
  * private repo  → anonymous feed is refused (404, like GitHub) and the
                    check explains that JARVIS_UPDATE_TOKEN is needed
  * private repo  → with JARVIS_UPDATE_TOKEN (a PAT) the feed and asset
                    downloads authenticate (Authorization: Bearer … seen by
                    the fake server) and work
  * no uploaded asset → falls back to the tag's source zip (API zipball with
                    a token / public archive URL without)
  * install       → downloaded bundle swaps code files, keeps .env + data,
                    backs up what it replaced, and refuses git checkouts

Exit 0 = the updater behaves on all fronts.

    python tests/update_sim.py
"""
from __future__ import annotations

import io
import json
import re
import shutil
import stat
import sys
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILED = []

REPO = "Mangooooonada/AI-pc"
TOKEN = "ghp_sim_secret_token_123"
VERSION = "9.9.9"
ZIP_BYTES = None  # filled in main()


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001 - sim reports everything
        FAILED.append(name)
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")


def make_zip(version: str = VERSION, prefix: bool = True) -> bytes:
    """A plausible JARVIS release zip (git-archive style, prefixed folder)."""
    bio = io.BytesIO()
    base = f"JARVIS-v{version}/" if prefix else ""
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(base + "main.py", 'print("sim release main")\n')
        zf.writestr(base + "jarvis/__init__.py", f'__version__ = "{version}"\n')
        zf.writestr(base + "jarvis/updater.py", "# sim copy of the updater\n")
        zf.writestr(base + "VERSION", version + "\n")
    return bio.getvalue()


class FakeGitHub(BaseHTTPRequestHandler):
    """Faithful-enough Releases API stand-in.

    Mode switches behaviour to mirror GitHub's public/private reality:
      * public  — feed + assets answer anonymously; a bad token → 401
      * private — feed/assets need a valid Bearer token; no token → 404
                  (GitHub hides private repos from anonymous callers),
                  a bad token → 401
    """

    mode = "public"
    assets = []          # list of asset dicts to attach to the latest release
    seen: list = []      # (path, Authorization header, Accept header)

    # ------------------------------------------------------------ helpers --
    def log_message(self, *args):  # silence the dev-log noise
        pass

    def _reply(self, code: int, payload, ctype: str = "application/json") -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth_ok(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _record(self, path: str) -> None:
        FakeGitHub.seen.append(
            (path, self.headers.get("Authorization", ""), self.headers.get("Accept", ""))
        )

    # ------------------------------------------------------------- routes --
    def do_GET(self) -> None:  # noqa: C901 - route table, intentionally flat
        self._record(self.path)
        p = self.path

        # GET /repos/{repo}/releases/latest
        m = re.match(r"^/repos/[^/]+/[^/]+/releases/latest$", p)
        if m:
            private = FakeGitHub.mode == "private"
            authed = self._auth_ok()
            if private and not authed and not self.headers.get("Authorization"):
                return self._reply(404, {"message": "Not Found"})
            if private and self.headers.get("Authorization") and not authed:
                return self._reply(401, {"message": "Bad credentials"})
            if not private and self.headers.get("Authorization") and not authed:
                return self._reply(401, {"message": "Bad credentials"})
            release = {
                "tag_name": f"v{VERSION}",
                "name": f"v{VERSION} — Sim",
                "html_url": f"http://127.0.0.1:{self.server.server_port}/releases/tag/v{VERSION}",
                "assets": FakeGitHub.assets,
            }
            return self._reply(200, release)

        # GET /repos/{repo}/releases/assets/{id}  (Accept: application/octet-stream)
        m = re.match(r"^/repos/[^/]+/[^/]+/releases/assets/(\d+)$", p)
        if m:
            if FakeGitHub.mode == "corrupt":  # serve a non-zip body
                return self._reply(200, b"this is definitely not a zip file",
                                   ctype="application/octet-stream")
            private = FakeGitHub.mode == "private"
            authed = self._auth_ok()
            if private and not authed:
                return self._reply(404 if not self.headers.get("Authorization") else 401,
                                   {"message": "Not Found"})
            return self._reply(200, ZIP_BYTES, ctype="application/octet-stream")

        # GET /repos/{repo}/zipball/{tag}  (authenticated source zip)
        m = re.match(r"^/repos/[^/]+/[^/]+/zipball/v[\d.]+$", p)
        if m:
            if not self._auth_ok():
                return self._reply(404 if not self.headers.get("Authorization") else 401,
                                   {"message": "Not Found"})
            return self._reply(200, ZIP_BYTES, ctype="application/zip")

        # GET /{repo}/archive/refs/tags/v{tag}.zip  (public source zip)
        m = re.match(r"^/[^/]+/[^/]+/archive/refs/tags/v[\d.]+\.zip$", p)
        if m:
            return self._reply(200, ZIP_BYTES, ctype="application/zip")

        return self._reply(404, {"message": f"no fake route for {p}"})


def main() -> int:
    global ZIP_BYTES
    ZIP_BYTES = make_zip()

    from jarvis import updater

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    FakeGitHub.seen = []

    def reset(mode: str, assets) -> None:
        FakeGitHub.mode = mode
        FakeGitHub.assets = assets
        FakeGitHub.seen = []

    try:
        # ---- anonymous, public repo: check + download -------------------
        def _anon_check():
            reset("public", [])
            info = updater.check_for_update(repo=REPO, api_base=base, timeout=5)
            assert info["ok"], info
            assert info["authenticated"] is False
            assert info["update_available"] is True, info  # 9.9.9 > local
            assert info["latest_version"] == VERSION
            assert all(not req[1] for req in FakeGitHub.seen), "no auth header may be sent"

        check("public repo: anonymous check finds a newer release", _anon_check)

        def _anon_download():
            reset("public", [{"id": 101, "name": f"JARVIS-v{VERSION}.zip",
                              "browser_download_url": f"{base}/x/JARVIS-v{VERSION}.zip",
                              "size": len(ZIP_BYTES)}])
            with tempfile.TemporaryDirectory() as td:
                out = updater.download_release(
                    {"tag_name": f"v{VERSION}", "assets": FakeGitHub.assets},
                    dest_dir=td, repo=REPO, api_base=base, timeout=5,
                )
                data = out.read_bytes()
            assert data == ZIP_BYTES
            asset_reqs = [s for s in FakeGitHub.seen if "/releases/assets/" in s[0]]
            assert asset_reqs, "the asset endpoint should have been hit"
            assert not asset_reqs[-1][1], "anonymous download must not send auth"

        check("public repo: anonymous asset download works, sends no token", _anon_download)

        # ---- private repo, no token: friendly refusal --------------------
        def _private_no_token():
            reset("private", [])
            info = updater.check_for_update(repo=REPO, api_base=base, timeout=5)
            assert info["ok"] is False
            assert "JARVIS_UPDATE_TOKEN" in info["error"], info["error"]
            assert info["kind"] == "empty" or info["kind"] == "auth"

        check("private repo: anonymous check explains JARVIS_UPDATE_TOKEN", _private_no_token)

        def _private_bad_token():
            reset("private", [])
            info = updater.check_for_update(repo=REPO, api_base=base,
                                            token="ghp_wrong", timeout=5)
            assert info["ok"] is False and info["kind"] == "auth", info

        check("private repo: a bad token is reported as an auth refusal", _private_bad_token)

        # ---- private repo, valid token: feed + asset download ------------
        def _private_token():
            reset("private", [])
            info = updater.check_for_update(repo=REPO, api_base=base, token=TOKEN, timeout=5)
            assert info["ok"] and info["authenticated"] is True, info
            assert info["update_available"] is True
            latest_reqs = [s for s in FakeGitHub.seen if s[0].endswith("/releases/latest")]
            assert latest_reqs[-1][1] == f"Bearer {TOKEN}", "feed must authenticate"

        check("private repo: token-authenticated feed check works", _private_token)

        def _private_download():
            reset("private", [{"id": 101, "name": f"JARVIS-v{VERSION}.zip",
                               "browser_download_url": f"{base}/x/JARVIS-v{VERSION}.zip",
                               "size": len(ZIP_BYTES)}])
            with tempfile.TemporaryDirectory() as td:
                out = updater.download_release(
                    {"tag_name": f"v{VERSION}", "assets": FakeGitHub.assets},
                    dest_dir=td, repo=REPO, api_base=base, token=TOKEN, timeout=5,
                )
                assert out.read_bytes() == ZIP_BYTES
            asset_reqs = [s for s in FakeGitHub.seen if "/releases/assets/" in s[0]]
            assert asset_reqs[-1][1] == f"Bearer {TOKEN}", "asset pull must authenticate"

        check("private repo: token-authenticated asset download works", _private_download)

        # ---- no uploaded asset: source-zip fallbacks ---------------------
        def _private_zipball():
            reset("private", [])
            with tempfile.TemporaryDirectory() as td:
                out = updater.download_release(
                    {"tag_name": f"v{VERSION}", "assets": []},
                    dest_dir=td, repo=REPO, api_base=base, token=TOKEN, timeout=5,
                )
                assert out.read_bytes() == ZIP_BYTES
            assert any("/zipball/" in s[0] for s in FakeGitHub.seen)

        check("private repo: no asset → token-authenticated source zip", _private_zipball)

        def _public_archive():
            reset("public", [])
            with tempfile.TemporaryDirectory() as td:
                out = updater.download_release(
                    {"tag_name": f"v{VERSION}", "assets": []},
                    dest_dir=td, repo=REPO, api_base=base, timeout=5,
                )
                assert out.read_bytes() == ZIP_BYTES
            assert any("/archive/refs/tags/" in s[0] for s in FakeGitHub.seen)

        check("public repo: no asset → anonymous source-zip archive", _public_archive)

        # ---- corrupt download is refused ----------------------------------
        def _corrupt_download():
            reset("corrupt", [])
            with tempfile.TemporaryDirectory() as td:
                try:
                    updater.download_release(
                        {"tag_name": f"v{VERSION}", "assets": [{"id": 202,
                         "name": "broken.zip", "browser_download_url": "x", "size": 0}]},
                        dest_dir=td, repo=REPO, api_base=base, timeout=5,
                    )
                    raise AssertionError("expected corrupt-zip refusal")
                except updater.UpdateError as exc:
                    assert exc.kind == "corrupt", exc.kind

        # ---- install mechanics (throwaway dirs, never the real repo) ------
        def _install_swaps_code_keeps_data():
            with tempfile.TemporaryDirectory() as td:
                target = Path(td) / "app"
                (target / "jarvis").mkdir(parents=True)
                (target / "data").mkdir()
                (target / "main.py").write_text("OLD MAIN\n")
                (target / "jarvis" / "__init__.py").write_text('__version__ = "1.2.8"\n')
                (target / ".env").write_text("SECRET=keepme\n")
                (target / "data" / "keep.txt").write_text("keep\n")
                zpath = Path(td) / "rel.zip"
                zpath.write_bytes(ZIP_BYTES)

                res = updater.install_update(zpath, target_dir=target)
                assert res["ok"], res
                assert "main.py" in res["installed"] and "jarvis" in res["installed"]
                assert (target / "main.py").read_text() == 'print("sim release main")\n'
                assert (target / "jarvis" / "updater.py").exists()
                assert (target / ".env").read_text() == "SECRET=keepme\n", ".env must survive"
                assert (target / "data" / "keep.txt").read_text() == "keep\n", "data must survive"
                # backup of the replaced main.py exists
                backups = list(Path(td).glob("app.backup-*/main.py"))
                assert backups and backups[0].read_text() == "OLD MAIN\n"

        check("install swaps code, keeps .env/data, backs up replaced files",
              _install_swaps_code_keeps_data)

        def _install_refuses_git_checkout():
            with tempfile.TemporaryDirectory() as td:
                target = Path(td) / "dev"
                (target / ".git").mkdir(parents=True)
                (target / "main.py").write_text("x")
                zpath = Path(td) / "rel.zip"
                zpath.write_bytes(ZIP_BYTES)
                try:
                    updater.install_update(zpath, target_dir=target)
                    raise AssertionError("expected git-checkout refusal")
                except updater.UpdateError as exc:
                    assert exc.kind == "unsafe", exc.kind

        check("install refuses to overwrite a git checkout", _install_refuses_git_checkout)

        def _install_into_fresh_dir():
            with tempfile.TemporaryDirectory() as td:
                zpath = Path(td) / "rel.zip"
                zpath.write_bytes(ZIP_BYTES)
                res = updater.install_update(zpath, target_dir=Path(td) / "brand-new")
                assert res["ok"] and (Path(td) / "brand-new" / "main.py").exists()

        check("install creates a fresh target dir", _install_into_fresh_dir)

        def _install_refuses_symlink_bundle():
            with tempfile.TemporaryDirectory() as td:
                bio = io.BytesIO()
                evil = io.BytesIO()
                with zipfile.ZipFile(evil, "w") as zf:
                    zi = zipfile.ZipInfo("main.py")
                    zi.external_attr = (stat.S_IFLNK | 0o777) << 16
                    zf.writestr(zi, "/tmp")
                zpath = Path(td) / "evil.zip"
                zpath.write_bytes(evil.getvalue())
                try:
                    updater.install_update(zpath, target_dir=Path(td) / "app")
                    raise AssertionError("expected symlink refusal")
                except updater.UpdateError as exc:
                    assert exc.kind == "corrupt", exc.kind

        check("install refuses symlink entries inside a bundle",
              _install_refuses_symlink_bundle)

        reset("corrupt", [])
        check("corrupt download is refused as corrupt", _corrupt_download)
        reset("public", [])

    finally:
        server.shutdown()
        server.server_close()

    print("=" * 46)
    if FAILED:
        print(f"FAILED: {len(FAILED)} — {', '.join(FAILED)}")
        return 1
    print("UPDATE SIM ALL GREEN — public + private feeds, token auth, install behave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
