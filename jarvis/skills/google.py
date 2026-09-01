"""Google scaffolding: Calendar + Gmail via OAuth desktop client.

Fully optional — the google-api libraries are imported lazily and every
skill degrades to a plain-English "connect Google first" message until:
  1. `pip install google-api-python-client google-auth-oauthlib` is run, and
  2. an OAuth Desktop `credentials.json` exists (repo root or workspace).

The cached OAuth token lives in <workspace>/google_token.json (gitignored).
Read-only scopes only: calendar.readonly + gmail.readonly.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Optional, Tuple

from . import skill
from ..config import config

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

_LIBS_NOTE = ("The Google libraries aren't installed yet. Run:\n"
              "  pip install google-api-python-client google-auth-oauthlib\n"
              "then ask again.")


def _libs() -> Optional[Tuple]:
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        return Credentials, Request, InstalledAppFlow, build
    except Exception:
        return None


def _credentials_path() -> Optional[Path]:
    try:
        return config.credentials_path()
    except Exception:
        return None


def _token_path() -> Path:
    try:
        return config.workspace / "google_token.json"
    except Exception:
        return Path.cwd() / "google_token.json"


def _connect_note(path: Optional[Path]) -> str:
    return (
        "Google isn't connected yet. To wire it up:\n"
        "1. In Google Cloud Console, create an OAuth client of type "
        "'Desktop app'.\n"
        "2. Download it as credentials.json into "
        f"{path or 'the Jarvis folder'}.\n"
        "3. Ask me again — the first run opens a browser sign-in, then the "
        "token is cached locally."
    )


def _get_service(api: str, version: str):
    """Return (service, error_message). error_message empty on success."""
    libs = _libs()
    if libs is None:
        return None, _LIBS_NOTE
    Credentials, Request, InstalledAppFlow, build = libs

    creds_file = _credentials_path()
    if creds_file is None:
        return None, _connect_note(config.workspace / "credentials.json")

    token = _token_path()
    creds = None
    try:
        if token.exists():
            creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not (creds and creds.valid):
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        try:
            token.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            pass
        return build(api, version, credentials=creds, cache_discovery=False), ""
    except FileNotFoundError:
        return None, f"credentials.json at {creds_file} isn't a readable file."
    except Exception as exc:
        msg = str(exc)
        if "invalid" in msg.lower() or "malformed" in msg.lower():
            return None, ("credentials.json doesn't look like an OAuth *Desktop* "
                          "client file. Download the Desktop-app client JSON and try again.")
        return None, f"Google sign-in didn't finish: {msg}"


@skill(
    "google_status",
    "Report whether Google (Calendar/Gmail) is connected: libraries installed, credentials file present, token cached.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["is google connected", "google status", "connect google",
              "connect my google account", "google setup"],
)
def google_status() -> str:
    lines = []
    libs_ok = _libs() is not None
    lines.append(f"Google libraries: {'installed' if libs_ok else 'missing'}")
    creds = _credentials_path()
    lines.append(f"credentials.json: {'found at ' + str(creds) if creds else 'not found'}")
    token = _token_path()
    lines.append(f"sign-in token: {'cached at ' + str(token) if token.exists() else 'not yet'}")
    if not libs_ok:
        lines.append("\n" + _LIBS_NOTE)
    elif creds is None:
        lines.append("\n" + _connect_note(config.workspace / "credentials.json"))
    elif not token.exists():
        lines.append("\nReady — first Calendar/Gmail request will open a browser sign-in.")
    else:
        lines.append("\nAll set — Calendar and Gmail are wired up.")
    return "\n".join(lines)


@skill(
    "list_calendar_events",
    "List upcoming Google Calendar events (next N days, default 3). Read-only.",
    {
        "type": "object",
        "properties": {"days": {"type": "integer", "description": "How many days ahead to look, default 3"}},
        "required": [],
    },
    triggers=["google calendar", "what's on my google calendar", "upcoming calendar events",
              "what's on my calendar", "check my calendar"],
)
def list_calendar_events(days: int | str = 3) -> str:
    service, err = _get_service("calendar", "v3")
    if service is None:
        return err
    try:
        n = max(1, min(14, int(str(days).strip() or 3)))
    except Exception:
        n = 3
    now = _dt.datetime.now(_dt.timezone.utc)
    until = now + _dt.timedelta(days=n)
    try:
        res = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=until.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=12,
        ).execute()
    except Exception as exc:
        return f"Google Calendar didn't answer: {exc}"
    events = res.get("items", [])
    if not events:
        return f"Nothing on your Google Calendar in the next {n} day(s). Clear skies."
    lines = [f"Next {n} day(s) on Google Calendar:"]
    for ev in events:
        start = ev.get("start", {})
        when = start.get("dateTime") or start.get("date") or "?"
        try:
            if "T" in when:
                dt = _dt.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone()
                when = dt.strftime("%a %b %d, %H:%M")
            else:
                dt = _dt.date.fromisoformat(when)
                when = dt.strftime("%a %b %d (all day)")
        except Exception:
            pass
        lines.append(f"  • {when} — {ev.get('summary', '(no title)')}")
    return "\n".join(lines)


@skill(
    "gmail_unread",
    "List unread Gmail subjects and senders (latest N, default 5). Read-only.",
    {
        "type": "object",
        "properties": {"count": {"type": "integer", "description": "How many unread messages to list, default 5"}},
        "required": [],
    },
    triggers=["check my gmail", "any unread emails", "gmail unread",
              "check gmail", "do i have new mail"],
)
def gmail_unread(count: int | str = 5) -> str:
    service, err = _get_service("gmail", "v1")
    if service is None:
        return err
    try:
        n = max(1, min(15, int(str(count).strip() or 5)))
    except Exception:
        n = 5
    try:
        res = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=n).execute()
        msgs = res.get("messages", [])
        if not msgs:
            return "Inbox zero — no unread mail. Nice."
        lines = [f"{len(msgs)} unread (showing newest):"]
        for m in msgs:
            meta = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
            hdr = {h["name"].lower(): h["value"]
                   for h in meta.get("payload", {}).get("headers", [])}
            sender = hdr.get("from", "?").split("<")[0].strip() or hdr.get("from", "?")
            lines.append(f"  • {sender}: {hdr.get('subject', '(no subject)')}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Gmail didn't answer: {exc}"
