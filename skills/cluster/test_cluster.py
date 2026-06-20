#!/usr/bin/env python3
"""Tests for the cluster scheduler — synthetic backends + temp state.

    python -m skills.cluster.test_cluster
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.llm_backends.discovery import Backend
from skills.cluster import cluster


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _mk(host, port, lat):
    return Backend(kind="lmstudio", label="LM Studio", host=host, port=port,
                   api="openai", chat=True, models=["m"], latency_ms=lat,
                   base_url=f"http://{host}:{port}")


def main() -> int:
    state = [0, 0]
    print("== cluster tests ==")

    fake = [_mk("a", 1234, 30), _mk("b", 1234, 10), _mk("c", 1234, 20)]
    _orig = cluster._chat_backends
    cluster._chat_backends = lambda: list(fake)
    with tempfile.TemporaryDirectory() as d:
        cluster._STATE = Path(d) / "state.json"
        try:
            # latency strategy → lowest latency (b:10)
            _ok("pick(latency) → lowest-latency backend",
                cluster.pick("latency")["host"] == "b", state)

            # lru spreads: 3 picks cover all 3 distinct hosts
            picks = [cluster.pick("lru")["host"] for _ in range(3)]
            _ok("pick(lru) spreads across all machines", set(picks) == {"a", "b", "c"}, state)
            # 4th pick reuses the least-recently-used (the first one picked)
            _ok("pick(lru) reuses least-recently-used next",
                cluster.pick("lru")["host"] == picks[0], state)
        finally:
            cluster._chat_backends = _orig

    # delegate with no endpoint → safe no-op with guidance
    os.environ.pop("BOTTE_AGENT_testhost", None)
    r = cluster.delegate("testhost", "do a thing")
    _ok("delegate without an endpoint is a safe no-op",
        r["delegated"] is False and "agent endpoint" in r["reason"], state)

    # no backends → pick returns None
    cluster._chat_backends = lambda: []
    try:
        _ok("pick returns None with no backends", cluster.pick() is None, state)
    finally:
        cluster._chat_backends = _orig

    # ── reference agent: whitelist + live roundtrip ──
    from skills.cluster import agent
    _ok("agent runs whitelisted read-only action (ping)",
        agent.handle_task({"task": "ping"})["ok"] is True, state)
    _ok("agent machine_status returns data",
        agent.handle_task({"task": "machine_status"}).get("result", {}).get("hostname"), state)
    bad = agent.handle_task({"task": "rm -rf /"})
    _ok("agent rejects non-whitelisted action (no shell)",
        bad["ok"] is False and "not allowed" in bad["error"], state)

    # live HTTP roundtrip: start the receiver, delegate to it, assert response
    import threading
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", 0), agent._make_handler(""))
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        r = cluster.delegate("127.0.0.1", "ping",
                             agent_url=f"http://127.0.0.1:{port}/task")
        import json as _json
        _ok("delegate → agent live roundtrip works",
            r["delegated"] is True and _json.loads(r["response"])["ok"] is True, state)
    finally:
        srv.shutdown(); srv.server_close()

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
