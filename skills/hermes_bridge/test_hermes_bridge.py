#!/usr/bin/env python3
"""Tests for the Hermes bridge — deterministic, offline (no LLM required for
the tools that only decide/search; graceful error strings for the ones that
need a live backend).

    python -m skills.hermes_bridge.test_hermes_bridge
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.hermes_bridge.bridge import TOOL_SCHEMAS, dispatch, mcp_config


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== hermes_bridge tests ==")

    cfg = mcp_config(python_exe="python", cwd="/x/botte-secrete")
    _ok("mcp_config produces a pasteable .mcp.json entry",
        cfg["mcpServers"]["botte-llm"]["args"] == ["-m", "skills.llm_mcp.server"]
        and cfg["mcpServers"]["botte-llm"]["cwd"] == "/x/botte-secrete", state)

    _ok("5 tool schemas match the roadmap's named tools",
        {s["name"] for s in TOOL_SCHEMAS} == {
            "botte_auto_route", "botte_local_chat", "botte_fusion",
            "botte_find_skills", "botte_infra_tips"}, state)
    _ok("every schema is OpenAI-function-calling shaped",
        all("parameters" in s and s["parameters"]["type"] == "object" for s in TOOL_SCHEMAS),
        state)

    out = dispatch("nonexistent_tool", {})
    _ok("dispatch reports an unknown tool instead of raising",
        "error" in json.loads(out) and "unknown tool" in json.loads(out)["error"], state)

    out = dispatch("botte_auto_route", {"prompt": "rename variable a to count"})
    parsed = json.loads(out)
    _ok("botte_auto_route dispatch returns a real routing decision",
        "mode" in parsed and "tier" in parsed, state)

    out = dispatch("botte_find_skills", {"query": "routing"})
    _ok("botte_find_skills dispatch returns without raising",
        isinstance(json.loads(out), (list, dict)), state)

    out = dispatch("botte_fusion", {"prompt": "hi", "strategy": "not_a_strategy"})
    _ok("botte_fusion rejects an invalid strategy with an error, not a crash",
        "error" in json.loads(out), state)

    out = dispatch("botte_infra_tips", {})
    _ok("botte_infra_tips dispatch never raises",
        isinstance(json.loads(out), (list, dict)), state)

    # local_chat and auto_route(execute=True) touch a real backend — assert the
    # bridge degrades to a clean error string rather than an uncaught exception
    # when no local model is reachable (best-effort resilience, not a network test).
    try:
        out = dispatch("botte_local_chat", {"prompt": "hi", "max_tokens": 8})
        json.loads(out)
        _ok("botte_local_chat dispatch never raises (error or real result)", True, state)
    except Exception:
        _ok("botte_local_chat dispatch never raises (error or real result)", False, state)

    # registry (from main's implementation) — both bridge styles coexist
    from skills.hermes_bridge.registry import SkillRegistry, get_registry, init_registry
    reg = SkillRegistry()
    _ok("registry lists skills", isinstance(reg.list_skills(), list), state)
    _ok("get_registry is a singleton", get_registry() is get_registry(), state)
    _ok("init_registry loads skills", len(init_registry()._skills) > 0, state)
    reg.register_function("test_func", lambda x: x * 2)
    _ok("registry register/get function round-trips",
        reg.get_function("test_func")(5) == 10, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
