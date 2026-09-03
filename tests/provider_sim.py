#!/usr/bin/env python3
"""Provider protocol simulation: Ollama + OpenAI/Groq-compatible + offline.

There is no real Ollama and no internet in a fresh sandbox, so this runs the
REAL provider code (jarvis.brain.providers) against faithful local stand-ins
for the two wire protocols:

  * Ollama:        GET /api/tags (model list) + POST /api/chat (JSON/NDJSON)
  * OpenAI/Groq:   GET /models + POST /chat/completions (JSON/SSE)
                   with the 401-poison / 429-throttle / 404 model-heal paths
  * Offline:       the keyword engine, no HTTP at all

Exit 0 = the provider layer behaves on all three fronts.

    python tests/provider_sim.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# This suite pokes providers that persist state (poison pills, throttle
# notices). Keep it out of the real Jarvis workspace: throwaway dir only.
os.environ.setdefault("JARVIS_WORKSPACE", tempfile.mkdtemp(prefix="jarvis-provider-sim-"))

FAILED = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001
        FAILED.append(name)
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ fake ---
class FakeOllama:
    """Faithful-enough Ollama: /api/tags + /api/chat (JSON + NDJSON stream)."""

    def __init__(self, models: list, chat_handler=None):
        self.models = models
        self.chat_handler = chat_handler or (lambda payload: {
            "message": {"role": "assistant", "content": "local hello"},
        })
        self.chat_hits: list = []
        self.tags_hits = 0
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, payload, ctype="application/json"):
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/tags":
                    fake.tags_hits += 1
                    self._send(200, {"models": [{"name": m} for m in fake.models]})
                else:
                    self._send(404, {"error": "nope"})

            def do_POST(self):
                if self.path != "/api/chat":
                    self._send(404, {"error": "nope"})
                    return
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                fake.chat_hits.append(payload)
                stream = bool(payload.get("stream"))
                model = payload.get("model")
                if model not in fake.models:
                    self._send(404, {"error": f"model '{model}' not found, try pulling it first"})
                    return
                if stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    for chunk in fake.chat_handler(payload).get("stream_chunks", []):
                        self.wfile.write((json.dumps(chunk) + "\n").encode())
                    self.wfile.flush()
                else:
                    out = fake.chat_handler(payload)
                    self._send(200, {
                        "model": model,
                        "message": out.get("message", {"role": "assistant",
                                                       "content": "local hello"}),
                        "done": True,
                    })

            def log_message(self, *a):
                pass

        return H

    def stop(self):
        self.server.shutdown()


class FakeOpenAI:
    """OpenAI-compatible brain (Groq flavour): /models + chat completions.

    Toggle `mode` per test: "ok" | "unauthorized" | "throttled" | "model_gone".
    """

    def __init__(self, model="llama-3.3-70b-versatile", mode="ok"):
        self.models = [model]
        self.mode = mode
        self.hits: list = []
        self.chooser = None  # (payload) -> message dict; set by tests
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def _json(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _sse(self, chunks):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in chunks:
                    self.wfile.write(
                        f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def do_GET(self):
                if self.path == "/models":
                    if fake.mode == "unauthorized":
                        self._json(401, {"error": "bad key"})
                        return
                    # A retired model: today's list has moved on, exactly the
                    # situation the self-heal exists for.
                    advertised = (["llama-live"] if fake.mode == "model_gone"
                                  else fake.models)
                    self._json(200, {"data": [{"id": m} for m in advertised]})
                else:
                    self._json(404, {"error": "nope"})

            def do_POST(self):
                if not self.path.endswith("/chat/completions"):
                    self._json(404, {"error": "nope"})
                    return
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                fake.hits.append(payload)
                if fake.mode == "unauthorized":
                    self._json(401, {"error": {"message": "invalid api key"}})
                    return
                if fake.mode == "throttled":
                    self._json(429, {"error": {"message": "rate limited"}})
                    return
                if fake.mode == "model_gone":
                    dead = fake.models[0]
                    if payload.get("model") == dead:
                        self._json(404, {"error": {"code": "model_not_found",
                                                   "message": "model not found"}})
                        return
                    # any other model (the healed one) answers normally
                if payload.get("stream"):
                    if fake.chooser:
                        msg = fake.chooser(payload)
                        content = msg.get("content") or ""
                        self._sse([
                            {"choices": [{"delta": {"role": "assistant"}}]},
                            *([{"choices": [{"delta": {"content": content}}]}]
                              if content else []),
                        ])
                    else:
                        self._sse([
                            {"choices": [{"delta": {"content": "groq streaming "}}]},
                            {"choices": [{"delta": {"content": "hello"}}]},
                        ])
                    return
                msg = fake.chooser(payload) if fake.chooser else {
                    "role": "assistant", "content": "groq hello"}
                self._json(200, {"choices": [{"message": msg}]})

            def log_message(self, *a):
                pass

        return H

    def stop(self):
        self.server.shutdown()


# ----------------------------------------------------------------- tests ---
def main() -> int:
    from jarvis.config import config

    def _ollama_chat_and_autopick():
        def handler(payload):
            if payload.get("stream"):
                return {"stream_chunks": [
                    {"message": {"role": "assistant", "content": "hi from the "}},
                    {"message": {"role": "assistant", "content": "local brain"}},
                    {"done": True},
                ]}
            return {"message": {"role": "assistant",
                                "content": "hi from the local brain"}}

        oll = FakeOllama(models=["llama3.1:8b", "qwen3:8b", "jarvis-tuned:latest"],
                         chat_handler=handler)
        try:
            saved = (config.ollama_host, config.ollama_model)
            config.ollama_host = oll.url()
            config.ollama_model = ""
            from jarvis.brain.providers import OllamaProvider, get_provider
            p = OllamaProvider()
            # Auto-pick preference: a personal fine-tune beats stock models.
            assert p.model == "jarvis-tuned:latest", p.model
            out = p.chat([{"role": "user", "content": "hello"}])
            assert out["content"] == "hi from the local brain"
            # Streaming path speaks the same language.
            parts: list = []
            p.chat_stream([{"role": "user", "content": "hi"}], None,
                          lambda t: parts.append(t))
            assert "".join(parts) == "hi from the local brain"
            # And get_provider('ollama') uses it directly.
            p2, _errs = get_provider("ollama")
            assert p2.name == "ollama"
        finally:
            config.ollama_host, config.ollama_model = saved
            oll.stop()

    check("Ollama: model autopick, JSON chat + NDJSON stream", _ollama_chat_and_autopick)

    def _ollama_self_heal_and_chat_404():
        oll = FakeOllama(models=["qwen3:8b"])
        try:
            saved = (config.ollama_host, config.ollama_model)
            config.ollama_host = oll.url()
            config.ollama_model = "ghost-model"
            from jarvis.brain.providers import OllamaProvider, ProviderError
            p = OllamaProvider()
            # An unpulled configured model self-heals onto an installed one
            # and SAYS so (no silent brick, no crash).
            assert p.model == "qwen3:8b", p.model
            assert p.note and "isn't pulled" in p.note, p.note
            # If the model vanishes between boot and chat, chat reports the
            # exact `ollama pull` remedy instead of a raw HTTP error.
            p.model = "ghost-model"
            try:
                p.chat([{"role": "user", "content": "hi"}])
                raise SystemExit("chat with a missing model should raise")
            except ProviderError as exc:
                assert "isn't installed" in str(exc) and "ollama pull" in str(exc)
        finally:
            config.ollama_host, config.ollama_model = saved
            oll.stop()

    check("Ollama: unpulled model self-heals; chat 404 says how to fix",
          _ollama_self_heal_and_chat_404)

    def _groq_chat_stream_and_tools():
        groq = FakeOpenAI()

        def chooser(payload):
            if payload.get("tools"):
                return {"role": "assistant", "content": None,
                        "tool_calls": [{"id": "call_1", "type": "function",
                                        "function": {"name": "get_time",
                                                     "arguments": "{}"}}]}
            return {"role": "assistant", "content": "groq hello"}

        groq.chooser = chooser
        try:
            saved = (config.openai_api_key, config.openai_base_url,
                     config.openai_model)
            config.openai_api_key = "gsk-fake"
            config.openai_base_url = groq.url()
            config.openai_model = "llama-3.3-70b-versatile"
            from jarvis.brain.providers import OpenAIProvider
            p = OpenAIProvider()
            assert p.base == groq.url()
            # non-stream chat with tool calls parsed into our shape
            out = p.chat([{"role": "user", "content": "what time is it"}],
                         tools=[{"type": "function", "function": {
                             "name": "get_time", "parameters": {}}}])
            assert out["tool_calls"][0]["name"] == "get_time"
            # SSE stream: tokens accumulate through the delta parser
            parts: list = []
            out = p.chat_stream([{"role": "user", "content": "hi"}], None,
                                lambda t: parts.append(t))
            assert "".join(parts) == "groq hello"
            assert out["content"] == "groq hello"
        finally:
            config.openai_api_key, config.openai_base_url, config.openai_model = saved
            groq.stop()

    check("Groq/OpenAI: chat, tool calls, SSE token stream", _groq_chat_stream_and_tools)

    def _groq_401_poison_and_429():
        groq = FakeOpenAI(mode="unauthorized")
        from jarvis import state
        saved_dead = dict(state._STATE.get("dead_credentials", {}))
        try:
            saved = (config.openai_api_key, config.openai_base_url,
                     config.openai_model)
            config.openai_api_key = "gsk-wrong"
            config.openai_base_url = groq.url()
            config.openai_model = "llama-3.3-70b-versatile"
            from jarvis.brain import providers as P
            # First call: 401 → poisoned + ProviderError.
            try:
                P.OpenAIProvider().chat([{"role": "user", "content": "hi"}])
                raise SystemExit("401 should raise")
            except P.ProviderError:
                pass
            assert "openai" in P._POISONED
            # Poison pill survives 'restarts' (permanent store)…
            assert P._permanent_poison_active("openai")
            # …so the next construction is refused without touching the wire.
            hits = len(groq.hits)
            try:
                P.OpenAIProvider()
                raise SystemExit("poisoned provider should refuse to build")
            except P.ProviderError:
                pass
            assert len(groq.hits) == hits  # no new HTTP call happened
            P._POISONED.clear()
        finally:
            config.openai_api_key, config.openai_base_url, config.openai_model = saved
            state._STATE["dead_credentials"] = saved_dead
            groq.stop()

        # 429 benches the provider for a cooldown and try_alternates skips it.
        groq2 = FakeOpenAI(mode="throttled")
        try:
            config.openai_api_key = "gsk-fake"
            config.openai_base_url = groq2.url()
            config.openai_model = "m"
            from jarvis.brain import providers as P
            P._THROTTLED.clear()
            try:
                P.OpenAIProvider().chat([{"role": "user", "content": "hi"}])
                raise SystemExit("429 should raise")
            except P.ProviderError:
                pass
            assert P.throttled("openai")
            # Failover must walk PAST a benched openai (all other brains dead
            # or tried → no candidate, never a throttled one).
            assert P.try_alternates("offline", {"offline", "ollama", "remote"}) is None
        finally:
            config.openai_api_key = ""
            P._THROTTLED.clear()
            groq2.stop()

    check("Groq/OpenAI: 401 poisons permanently, 429 benches for cooldown",
          _groq_401_poison_and_429)

    def _groq_model_self_heal():
        gone = FakeOpenAI(model="llama-dead-name", mode="model_gone")
        from pathlib import Path as _P
        env = _P(".env")
        had_env = env.exists()
        env_before = env.read_text(encoding="utf-8") if had_env else ""
        try:
            saved = (config.openai_api_key, config.openai_base_url,
                     config.openai_model)
            config.openai_api_key = "gsk-x"
            config.openai_base_url = gone.url()
            config.openai_model = "llama-dead-name"
            from jarvis.brain.providers import OpenAIProvider
            o = OpenAIProvider()
            out = o.chat([{"role": "user", "content": "x"}])
            assert out["content"] == "groq hello", out
            # The provider healed itself onto the advertised live model and
            # persisted it so the next boot starts healthy.
            assert o.model == "llama-live", o.model
            assert "OPENAI_MODEL=llama-live" in env.read_text(encoding="utf-8")
        finally:
            config.openai_api_key, config.openai_base_url, config.openai_model = saved
            if had_env:
                env.write_text(env_before, encoding="utf-8")
            else:
                env.unlink(missing_ok=True)
            gone.stop()

    check("Groq/OpenAI: dead model self-heals after 404", _groq_model_self_heal)

    def _auto_router_both_brains():
        """auto with BOTH brains up → RouterProvider: light→local, heavy→cloud."""
        oll = FakeOllama(models=["qwen3:8b"])
        groq = FakeOpenAI()
        try:
            saved = (config.ollama_host, config.openai_api_key,
                     config.openai_base_url, config.openai_model)
            config.ollama_host = oll.url()
            config.openai_api_key = "gsk-x"
            config.openai_base_url = groq.url()
            config.openai_model = "llama-3.3-70b-versatile"
            from jarvis.brain.providers import get_provider, RouterProvider
            p, errs = get_provider("auto")
            assert isinstance(p, RouterProvider), (type(p).__name__, errs)
            # light chat → local ollama endpoint
            p.chat([{"role": "user", "content": "good morning"}])
            assert oll.chat_hits and groq.hits == []
            # heavy turn → cloud endpoint
            p.chat([{"role": "user", "content": "write me an essay about the sea"}])
            assert groq.hits, "heavy turn should hit the cloud brain"
            # strict privacy pins every turn local
            config.privacy_mode = "strict"
            before = len(groq.hits)
            p.chat([{"role": "user", "content": "write me an essay about stars"}])
            assert len(groq.hits) == before
            config.privacy_mode = "guarded"
        finally:
            config.ollama_host, config.openai_api_key, config.openai_base_url, \
                config.openai_model = saved
            oll.stop(); groq.stop()

    check("Auto router: quick→local, heavy→cloud, strict pins local", _auto_router_both_brains)

    def _offline_engine():
        from jarvis.brain.agent import Agent
        ag = Agent("offline")
        assert ag.provider_name == "offline"
        # Greeting works with zero HTTP anywhere.
        assert "Systems nominal" in ag.ask("hello").reply
        # Keyword command fires a real skill through the offline engine.
        t = ag.ask("what time is it")
        assert t.reply, "offline skill should have answered"
        assert t.provider == "offline"
        # Refusals / junk never crash it.
        assert isinstance(ag.ask("💀" * 400).reply, str)

    check("Offline: greetings, keyword skills, junk-proof", _offline_engine)

    def _offline_upgrade_probe_honors_remote():
        """When JARVIS_PROVIDER=remote is configured but the remote is down,
        boot lands on offline and notes WHY (never silent)."""
        from jarvis.config import config
        saved = (config.provider, config.remote_url)
        config.provider = "remote"
        config.remote_url = "http://127.0.0.1:1"
        try:
            from jarvis.brain.providers import get_provider
            p, errs = get_provider(None)
            assert p.name == "offline"
            assert any("remote" in e for e in errs), errs
        finally:
            config.provider, config.remote_url = saved

    check("Remote down at boot: offline + an explanatory note", _offline_upgrade_probe_honors_remote)

    print("=" * 46)
    if FAILED:
        print(f"FAILED: {len(FAILED)} — {', '.join(FAILED)}")
        return 1
    print("PROVIDER SIM ALL GREEN — Ollama / Groq-compatible / offline behave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
