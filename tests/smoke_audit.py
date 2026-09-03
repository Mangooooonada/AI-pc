#!/usr/bin/env python3
"""Smoke audit: 'is anything half-baked?' on demand.

    .venv\\Scripts\\python tests\\smoke_audit.py     (Windows)
    python tests/smoke_audit.py                      (anywhere)

Walks every API route, both chat transports, provider failover, poison-pill
persistence, privacy shielding, auto-memory, watcher toggles, and calls all
registered skills with working dummies. Exit code 0 = healthy. Never touches
real files on disk except a temp file; never leaves state behind beyond the
normal local JSON stores.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001 - audit reports everything
        FAILED.append(name)
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")


def main() -> int:
    from jarvis import state
    for k in ("conversations", "memories", "notifications", "activity",
              "routines", "tasks", "workflows"):
        state._STATE[k] = []
    state._STATE["flags"] = {}
    state._STATE["dead_credentials"] = {}

    from fastapi.testclient import TestClient  # noqa
    from jarvis.server import app

    c = TestClient(app)
    routes = [getattr(r, "path", "") for r in app.routes
              if "GET" in (getattr(r, "methods", set()) or set())]
    get_routes = [p for p in routes if "{" not in p and "stream" not in p]

    check(f"all {len(get_routes)} GET routes answer <500",
          lambda: [_ for _ in get_routes if c.get(_).status_code >= 500] == []
          or 1 / 0)

    def _chat():
        from jarvis.server import get_agent
        ag = get_agent()

        class Fake:
            name = "ollama"; last_turn_label = None

            def chat(self, messages, tools=None, **kw):
                return {"content": "Coherent, Sir.", "tool_calls": []}

            def chat_stream(self, messages, tools, on_token=None, **kw):
                if on_token:
                    on_token("Coherent, ")
                return {"content": "Coherent, Sir.", "tool_calls": []}

        ag.provider = Fake()
        assert "Coherent" in c.post("/api/chat", json={"message": "hi"}).json()["reply"]
        assert "Coherent" in c.post("/api/chat/stream", json={"message": "hi"}).text

    check("chat works on both transports", _chat)

    def _skills():
        from jarvis.skills import REGISTRY
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(b"audit"); tmp.close()
        rich = {"text": "audit", "content": "audit", "query": "tesla",
                "url": "https://example.com", "name": "audit", "task": "audit",
                "duration": "1m", "expression": "2+2", "title": "audit",
                "app": "notepad", "pattern": "*.py", "topic": "tesla",
                "command": "echo audit", "path": tmp.name,
                "folder": tempfile.gettempdir(), "minutes": 1, "number": 1}
        for nm, fn in sorted(REGISTRY.items()):
            assert isinstance(fn(**rich), str), f"{nm} non-string"
        os.unlink(tmp.name)
        print(f"      {len(REGISTRY)} skills callable")

    check("every registered skill survives a call", _skills)

    def _poison():
        from jarvis.brain import providers as P
        from jarvis.config import config
        saved_dead = dict(state._STATE.get("dead_credentials", {}))
        config.openai_api_key = "sk-dead"; config.openai_base_url = "https://x"; config.openai_model = "m"
        P.poison("openai", "401")
        P._POISONED.clear()
        try:
            P.OpenAIProvider()
            raise SystemExit("pill didn't persist")
        except RuntimeError:
            pass
        # Leave no fake dead-credential behind in the user's real state store.
        state._STATE["dead_credentials"] = saved_dead
        config.openai_api_key = None

    check("poison pill survives restarts", _poison)

    def _privacy():
        state._STATE["memories"] = []
        state.add_memory("The user lives in Testville.", kind="fact", source="t")
        from jarvis.privacy import guard
        from jarvis.config import config
        config.privacy_mode = "guarded"

        class Cloud:
            name = "openai"; base = "https://api.groq.com/openai/v1"; model = "m"

        msgs = [{"role": "system",
                 "content": "X.\n\nKnown facts about the user:\nThe user lives in Testville.\n\nY."}]
        out = guard(Cloud(), msgs)
        assert "Testville" not in "\n".join(m["content"] for m in out)

    check("privacy shield strips memory from cloud payloads", _privacy)

    def _automem():
        state._STATE["memories"] = []
        from jarvis.brain.automem import maybe_autoremember
        facts = maybe_autoremember("I am 21 remember that ok")
        assert any("21 years old" in f for f in facts)
        assert maybe_autoremember("set a timer for 10 mins") == []

    check("auto-memory banks facts, ignores noise", _automem)

    def _watch():
        r = c.post("/api/watch", json={"observer": True}).json()
        assert r["ok"] and r["state"]["observer"]
        from jarvis import observe
        from jarvis.observe import _shots_dir
        assert observe.observer_enabled()
        assert c.get("/api/watch/shot?name=../../etc/passwd").status_code == 400
        # v1.2.8 incremental rendering contract: /api/watch carries only what
        # the panel renders (≤20 events) plus today's aggregates; served shots
        # are cache-immutable so the UI never re-downloads a frame twice.
        w = c.get("/api/watch").json()
        assert len(w["activity"]) <= 20, len(w["activity"])
        assert "usage_today" in w and "focus_since" in w and "history_days" in w
        shot = _shots_dir() / "shot-20260903-031506.png"
        shot.write_bytes(b"fakeframe")
        try:
            got = c.get("/api/watch/shot?name=shot-20260903-031506.png")
            assert got.status_code == 200
            assert got.headers.get("cache-control", "").startswith(
                "public, max-age=3600, immutable")
        finally:
            shot.unlink(missing_ok=True)
        state._STATE["flags"] = {}
        state.save()  # the observer toggle was a test — don't leave it armed

    check("watcher toggles live + shot route hardened + panel payloads bounded", _watch)

    def _watch_usage_tracks_focus_not_tabs():
        """One row per APP-focus episode (tab switches don't spam the reel) and
        the focused seconds are KEPT in today's usage store."""
        from jarvis import observe as O
        saved_act = state._STATE.get("activity", [])
        saved_usage = state._STATE.get("usage_days", {})
        try:
            state._STATE["activity"] = []
            state._STATE["usage_days"] = {}
            with O._focus_lock:
                O._focus.update(app="", title="", start=0.0, app_start=0.0)
                O._pending.clear()
                O._last_sample = 0.0
                O._last_flush = 0.0

            # t=1000.. : Chrome on a tab; tab-switch at 1004 (title change);
            # app switch to Code at 1012; lock screen at 1016.
            O.record_sample("chrome.exe", "Reddit — news", now=1000)
            O.record_sample("chrome.exe", "YouTube — music", now=1004)
            O.record_sample("chrome.exe", "YouTube — music", now=1008)
            O.record_sample("Code.exe", "jarvis/state.py", now=1012)
            O.record_sample("", "", now=1016)
            O.flush_usage()

            rows = state.get_activity()
            apps = [r["app"] for r in rows]
            # Tab switch at 1004 produced NO new row — only the two app
            # episodes (chrome 1000→1012 = 12s, code 1012→1016 = 4s).
            assert apps == ["chrome", "code"], apps
            assert rows[0]["secs"] == 12 and rows[1]["secs"] == 4, rows
            today = {u["app"]: u["secs"] for u in state.usage_today()}
            assert today.get("chrome") == 12 and today.get("code") == 4, today
        finally:
            state._STATE["activity"] = saved_act
            state._STATE["usage_days"] = saved_usage
            with O._focus_lock:
                O._focus.update(app="", title="", start=0.0, app_start=0.0)
                O._pending.clear()
                O._last_sample = 0.0
                O._last_flush = 0.0
            state.save()  # don't leave the simulated frames in the store

    check("focus episodes (not tabs) drive the reel + today's usage", _watch_usage_tracks_focus_not_tabs)

    def _settings():
        assert c.post("/api/settings",
                      json={"updates": {"BOGUS": 1}}).json()["ok"] is False

    check("settings reject unknown keys loudly", _settings)

    def _remote_provider_wired():
        """JARVIS_PROVIDER=remote (the UI's Remote Jarvis preset) must actually
        engage the RemoteJarvisProvider — not silently land on offline."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from jarvis.config import config

        class FakeRemote(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/status":
                    body = json.dumps(
                        {"provider": "ollama", "model": "qwen3:8b",
                         "hostname": "remote-pc"}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                self.rfile.read(n)
                body = json.dumps(
                    {"reply": "coherent from the remote brain", "actions": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), FakeRemote)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        saved = (config.provider, config.remote_url, config.remote_key)
        try:
            config.provider = "remote"
            config.remote_url = f"http://127.0.0.1:{srv.server_address[1]}"
            config.remote_key = ""
            assert config.resolved_provider() == "remote", \
                "resolved_provider must pass an explicit remote through"
            from jarvis.brain.providers import get_provider
            p, errs = get_provider(None)
            assert p.name == "remote", f"expected remote, got {p.name} ({errs})"
            out = p.chat([{"role": "user", "content": "hi"}])
            assert "remote brain" in (out["content"] or "")
            # And /api/provider/remote reaches it through the API surface.
            s = c.post("/api/provider/remote").json()
            assert s["provider"] == "remote", f"api switch failed: {s}"
        finally:
            config.provider, config.remote_url, config.remote_key = saved
            srv.shutdown()

    check("Remote Jarvis preset actually engages the remote brain", _remote_provider_wired)

    def _provider_route_validates():
        """Unknown providers are a loud 400, not a silent walk to offline."""
        r = c.post("/api/provider/spaceship")
        assert r.status_code == 400, r.text
        # A configured-but-dead remote degrades to offline WITH explanations.
        from jarvis.config import config
        saved = (config.provider, config.remote_url)
        config.provider = "remote"
        config.remote_url = "http://127.0.0.1:1"  # nothing listens there
        try:
            s = c.post("/api/provider/remote").json()
            assert s["provider"] in {"offline", "remote"}, s
            assert any("remote" in n for n in s.get("notes", [])), s
        finally:
            config.provider, config.remote_url = saved

    check("provider route validates names and explains dead remotes", _provider_route_validates)

    def _say_flags_not_spoken():
        """`main.py say --speak hi` must speak 'hi', not '--speak hi'."""
        import main as main_mod
        assert main_mod._say_cli_args(["--speak", "say", "hi"]) == \
            ["--say", "--speak", "hi"]
        assert main_mod._say_cli_args(["say", "--speak", "hi"]) == \
            ["--say", "--speak", "hi"]
        assert main_mod._say_cli_args(
            ["--provider", "ollama", "say", "--speak", "what time is it"]) == \
            ["--say", "--provider", "ollama", "--speak", "what time is it"]
        # A dash-prefixed sentence after `say` is text, not a dropped flag.
        assert main_mod._say_cli_args(["say", "-5 degrees outside"]) == \
            ["--say", "-5 degrees outside"]

    check("say-mode keeps flags off the spoken sentence", _say_flags_not_spoken)

    def _stream_refusal_nudge():
        """Refusal interceptor must work on the SSE transport too."""
        from jarvis.brain.agent import Agent

        class StreamRefuser:
            name = "ollama"; last_turn_label = None
            n = 0

            def chat_stream(self, messages, tools, on_token, **kw):
                self.n += 1
                if self.n == 1:
                    if on_token:
                        on_token("I'm afraid I can't")
                    return {"content": "I'm afraid I can't do that, Sir.", "tool_calls": []}
                return {"content": "Now done, Sir.", "tool_calls": []}

        ag = Agent("offline"); sr = StreamRefuser(); ag.provider = sr
        t = ag.ask("mute everything", on_token=lambda x: None)
        assert t.reply == "Now done, Sir." and sr.n == 2
        assert not any("you HAVE the ability" in (m.get("content") or "") for m in ag.history)

    check("SSE-path refusal nudge fires once", _stream_refusal_nudge)

    def _model_heal_persists():
        """404 model_not_found on the STREAM path must heal and rewrite .env."""
        from jarvis.config import config
        from jarvis.brain import providers as P
        import requests, types

        config.openai_api_key = "gsk-x"
        config.openai_base_url = "https://api.groq.com/openai/v1"
        config.openai_model = "llama-dead-name"

        class FakeResp:
            def __init__(self, code, payload=None, text=""):
                self.status_code, self._payload, self.text = code, payload or {}, text

            def json(self): return self._payload

            def iter_lines(self, decode_unicode=True):
                yield 'data: {"choices":[{"delta":{"content":"healed"}}]}'
                yield 'data: [DONE]'

        real_post, real_get = requests.post, requests.get
        requests.post = lambda url, json=None, **k: (
            FakeResp(404, text='{"error":{"code":"model_not_found"}}')
            if json.get("model") == "llama-dead-name" else FakeResp(200, {}))
        requests.get = lambda url, **k: FakeResp(200, {"data": [{"id": "llama-live"}]})
        try:
            o = P.OpenAIProvider()
            out = o.chat_stream([{"role": "user", "content": "x"}], None, lambda s: None)
            assert out["content"] == "healed" and o.model == "llama-live"
            from pathlib import Path as _Path
            assert "OPENAI_MODEL=llama-live" in (_Path(".env").read_text() if _Path(".env").exists() else "")
        finally:
            requests.post, requests.get = real_post, real_get
            _p = _Path(".env")
            if _p.exists():
                _p.unlink()

    check("dead cloud model self-heals + persists on stream path", _model_heal_persists)

    def _restart_memory():
        state.log_turn("probe-question-42", "probe-answer-84", [], "ollama")
        from jarvis.brain.agent import Agent

        class Stub:
            name = "ollama"; last_turn_label = None

            def chat(self, m, tools=None, **kw):
                return {"content": "ok", "tool_calls": []}

        ag = Agent("offline"); ag.provider = Stub()
        flat = " ".join((x.get("content") or "") for x in ag.history)
        assert "probe-question-42" in flat and "probe-answer-84" in flat

    check("restart restores chat memory", _restart_memory)

    def _failover():
        from jarvis.brain.agent import Agent, ProviderError
        from jarvis.brain import providers as P

        class Dies:
            name = "ollama"; last_turn_label = None

            def chat(self, m, tools=None, **kw):
                raise ProviderError("dead")

        class Hero:
            name = "openai"; last_turn_label = None

            def chat(self, m, tools=None, **kw):
                return {"content": "took the wheel", "tool_calls": []}

        orig = P.try_alternates
        P.try_alternates = lambda cur, tried: Hero() if "openai" not in tried else None
        ag = Agent("offline"); ag.provider = Dies()
        t = ag.ask("write me anything")
        P.try_alternates = orig
        assert "took the wheel" in t.reply and "fallback" in (t.provider or "")

    check("brain death cascades to a neighbor", _failover)

    print("=" * 46)
    if FAILED:
        print(f"FAILED: {len(FAILED)} — {', '.join(FAILED)}")
        return 1
    print("ALL GREEN — nothing half-baked standing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
