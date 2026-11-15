#!/usr/bin/env python3
"""Tests for the cluster scheduler — synthetic backends + temp state.

    python -m skills.cluster.test_cluster
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

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
    guard = Mock()
    guard.reserve.return_value = {"allowed": True, "reason": "ok"}
    guard.check.return_value = {"allowed": True, "reason": "ok"}
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
        with patch.object(agent, "HostMemoryGuard", return_value=guard):
            r3 = agent.handle_task({"task": {"action": "run",
                                             "args": {"name": "safe_echo", "confirm": True}}})
        _ok("approved maintenance command runs with confirm",
            r3["ok"] is True and "done" in r3["output"], state)
        key, budget = guard.reserve.call_args.args
        _ok("maintenance reserves the default RAM budget and retains it after exit",
            budget == 4 * 1024 ** 3 and guard.check.call_args.args == (key,)
            and not guard.release.called and r3.get("reservation_retained") is True
            and r3.get("reservation_key") == key, state)
        _ok("list_commands exposes the whitelist (read-only)",
            agent.handle_task({"task": "list_commands"})["result"].get("safe_echo") == "test cmd",
            state)
    finally:
        agent._COMMANDS = _saved

    _test_memory_admission(agent, state)

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


def _test_memory_admission(agent, state):
    """No host ledger or machine commands: inject pressure and runner outcomes."""
    saved = agent._COMMANDS
    agent._COMMANDS = {"fixture": {"cmd": ["fixture-command"], "desc": "fixture",
                                   "estimated_ram_gib": 0.5}}
    try:
        for confirmed, name in ((False, "fixture"), (True, "unknown")):
            with patch.object(agent, "HostMemoryGuard") as factory:
                agent._run_named(name, confirmed)
                _ok("unauthorized/unconfirmed commands never reserve RAM",
                    not factory.called, state)

        guard = Mock()
        guard.reserve.return_value = {"allowed": False, "reason": "insufficient_ram"}
        with patch.object(agent, "HostMemoryGuard", return_value=guard), patch("subprocess.run") as run:
            result = agent._run_named("fixture", True)
            _ok("low memory refuses maintenance before subprocess",
                not result["ok"] and not run.called and not guard.release.called, state)

        guard = Mock()
        guard.reserve.return_value = {"allowed": True}
        guard.check.return_value = {"allowed": False, "reason": "pressure_changed"}
        with patch.object(agent, "HostMemoryGuard", return_value=guard), patch("subprocess.run") as run:
            result = agent._run_named("fixture", True)
            key, budget = guard.reserve.call_args.args
            _ok("fresh pressure recheck prevents start and releases unused budget",
                not result["ok"] and not run.called and budget == 512 * 1024 ** 2
                and guard.release.call_args.args == (key,), state)

        guard = Mock()
        guard.reserve.return_value = {"allowed": True}
        guard.check.side_effect = OSError("probe failed")
        with patch.object(agent, "HostMemoryGuard", return_value=guard), patch("subprocess.run") as run:
            result = agent._run_named("fixture", True)
            _ok("recheck failure remains closed without running a command",
                not result["ok"] and not run.called and guard.release.called, state)

        for error in (subprocess.TimeoutExpired("fixture-command", 1), OSError("spawn uncertain")):
            guard = Mock()
            guard.reserve.return_value = {"allowed": True}
            guard.check.return_value = {"allowed": True}
            with patch.object(agent, "HostMemoryGuard", return_value=guard), patch("subprocess.run", side_effect=error):
                result = agent._run_named("fixture", True)
                _ok("uncertain command keeps its reservation for reconciliation",
                    not result["ok"] and result.get("reservation_retained") is True
                    and result.get("reservation_key") == guard.reserve.call_args.args[0]
                    and not guard.release.called, state)

        for returncode in (0, 7):
            guard = Mock()
            guard.reserve.return_value = {"allowed": True}
            guard.check.return_value = {"allowed": True}
            with patch.object(agent, "HostMemoryGuard", return_value=guard), patch(
                    "subprocess.run", return_value=subprocess.CompletedProcess([], returncode, "done", "")):
                result = agent._run_named("fixture", True)
                _ok(f"command exit {returncode} retains RAM until descendant/service stop is checked",
                    result["ok"] is (returncode == 0) and result["exit"] == returncode
                    and result.get("reservation_retained") is True
                    and result.get("reservation_key") == guard.reserve.call_args.args[0]
                    and "descendants/services" in result.get("reservation_note", "")
                    and not guard.release.called, state)

        invalid = (True, False, 0, -1, 0.1, 1025, "4", None, float("nan"), float("inf"))
        for budget in invalid:
            agent._COMMANDS["fixture"]["estimated_ram_gib"] = budget
            with patch.object(agent, "HostMemoryGuard") as factory, patch("subprocess.run") as run:
                result = agent._run_named("fixture", True)
                _ok(f"invalid RAM budget {budget!r} does not fall back or launch",
                    not result["ok"] and not factory.called and not run.called, state)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.json"
            path.write_text(json.dumps({"commands": {
                "legacy": {"cmd": ["fixture"], "desc": "legacy"},
                "specific": {"cmd": ["fixture"], "estimated_ram_gib": 0.5},
                "bad": {"cmd": ["fixture"], "estimated_ram_gib": True}}}), encoding="utf-8")
            commands = agent.load_commands(path)
            _ok("whitelist preserves valid RAM budgets and excludes invalid estimates",
                commands["legacy"]["estimated_ram_gib"] == 4
                and commands["specific"]["estimated_ram_gib"] == 0.5 and "bad" not in commands, state)

        sample = {"available_bytes": 1, "total_bytes": 64 * 1024 ** 3,
                  "measured_at_utc": "2026-10-31T00:00:00Z"}
        with patch.object(agent, "HostMemoryGuard") as factory, patch.object(agent, "probe_memory", return_value=sample):
            result = agent.handle_task({"task": "machine_status"})
            ping = agent.handle_task({"task": "ping"})
            _ok("diagnostics expose fresh measurements and remain available under pressure",
                result["ok"] and result["result"]["memory"] == sample
                and ping["ok"] and not factory.called, state)
        with patch.object(agent, "probe_memory", side_effect=OSError("unavailable")):
            result = agent.handle_task({"task": "machine_status"})
            _ok("missing memory measurement is reported as unknown",
                result["ok"] and result["result"]["memory"]["status"] == "unknown", state)
    finally:
        agent._COMMANDS = saved


if __name__ == "__main__":
    raise SystemExit(main())
