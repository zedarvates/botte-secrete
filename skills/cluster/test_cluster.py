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

from skills.console_utf8 import force_utf8
from skills.llm_backends.discovery import Backend
from skills.cluster import cluster

force_utf8()


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
    r = cluster.delegate("10.0.0.8", "ping",
                         agent_url="http://127.0.0.1:8799/task", token="secret")
    _ok("delegate rejects endpoint host mismatch",
        r["delegated"] is False and "host must match" in r["reason"], state)
    r = cluster.delegate("10.0.0.8", "ping",
                         agent_url="http://10.0.0.8:8799/task", token="secret")
    _ok("delegate requires HTTPS away from loopback",
        r["delegated"] is False and "require https" in r["reason"], state)
    r = cluster.delegate("agent.local", "ping",
                         agent_url="https://agent.local/task")
    _ok("delegate requires a token away from loopback",
        r["delegated"] is False and "require a token" in r["reason"], state)

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

    # ── operator-approved maintenance whitelist (confirm-gated) ──
    _saved = agent._COMMANDS
    agent._COMMANDS = {"safe_echo": {"cmd": [sys.executable, "-c", "print('done')"],
                                     "desc": "test cmd"}}
    try:
        # run without confirm → refused, shows what it would run
        r1 = agent.handle_task({"task": {"action": "run", "args": {"name": "safe_echo"}}})
        _ok("maintenance run without confirm is refused",
            r1["ok"] is False and "confirmation required" in r1["error"], state)
        # run a name not in the whitelist → refused (no arbitrary command)
        r2 = agent.handle_task({"task": {"action": "run",
                                         "args": {"name": "rm_rf", "confirm": True}}})
        _ok("maintenance run of an unlisted name is refused",
            r2["ok"] is False and "not permitted" in r2["error"], state)
        # approved name + confirm → actually runs the operator's command
        r3 = agent.handle_task({"task": {"action": "run",
                                         "args": {"name": "safe_echo", "confirm": True}}})
        _ok("approved maintenance command runs with confirm",
            r3["ok"] is True and "done" in r3["output"], state)
        _ok("list_commands exposes the whitelist (read-only)",
            agent.handle_task({"task": "list_commands"})["result"].get("safe_echo") == "test cmd",
            state)
    finally:
        agent._COMMANDS = _saved

    # live HTTP roundtrip: start the receiver, delegate to it, assert response
    import threading
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", 0), agent._make_handler("secret"))
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        r = cluster.delegate("127.0.0.1", "ping",
                             agent_url=f"http://127.0.0.1:{port}/task",
                             token="secret")
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
