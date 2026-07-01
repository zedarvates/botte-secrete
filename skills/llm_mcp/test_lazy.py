#!/usr/bin/env python3
"""Tests for lazy tool loading — the ToolSearch pattern on our own MCP server.

    python -m skills.llm_mcp.test_lazy
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.llm_mcp.lazy import find_tool, lazy_tool_list, lazy_enabled, CORE_TOOL_NAMES
from skills.llm_mcp.server import TOOLS, DISPATCH, handle


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== lazy tool loading tests ==")

    # sanity: every declared core tool actually exists in TOOLS (catches typos)
    real_names = {t["name"] for t in TOOLS}
    _ok("every CORE_TOOL_NAMES entry exists in TOOLS",
        CORE_TOOL_NAMES <= real_names, state)
    _ok("every core tool is also dispatchable",
        CORE_TOOL_NAMES <= set(DISPATCH), state)

    # lazy_tool_list: small, core + find_tool, way under the full catalog
    lazy_list = lazy_tool_list(TOOLS)
    lazy_names = {t["name"] for t in lazy_list}
    _ok("lazy list includes find_tool", "find_tool" in lazy_names, state)
    _ok("lazy list includes exactly the core tools + find_tool",
        lazy_names == CORE_TOOL_NAMES | {"find_tool"}, state)
    _ok("lazy list is much smaller than the full catalog",
        len(lazy_list) < len(TOOLS) / 2, state)

    # find_tool: strong match on a tool's own name → full schema attached
    r = find_tool("classify skills relevant to a task", TOOLS)
    top_names = [m["name"] for m in r["matches"]]
    _ok("find_tool surfaces find_skills for a skill-search query",
        "find_skills" in top_names, state)
    strong = next((m for m in r["matches"] if m["score"] >= 1.0), None)
    _ok("a strong match carries the full inputSchema",
        strong is not None and strong.get("inputSchema") is not None, state)
    weak = next((m for m in r["matches"] if m["score"] < 1.0), None)
    if weak:
        _ok("a weak match omits the schema (keeps the reply small)",
            "inputSchema" not in weak, state)
    _ok("find_tool is 0 cloud tokens", r["cloud_tokens"] == 0, state)

    # find_tool: no plausible match → empty, no crash
    r0 = find_tool("xyzzy_no_such_concept_qqq", TOOLS)
    _ok("no-match query returns an empty match list, not an error",
        r0["matches"] == [], state)

    # find_tool: determinism
    _ok("find_tool is deterministic",
        find_tool("route a task locally", TOOLS) == find_tool("route a task locally", TOOLS),
        state)

    # protocol-level: tools/list is lazy by default
    saved = os.environ.pop("BOTTE_MCP_LAZY_TOOLS", None)
    try:
        resp = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        _ok("tools/list is lazy by default (small)",
            len(resp["result"]["tools"]) == len(CORE_TOOL_NAMES) + 1, state)

        os.environ["BOTTE_MCP_LAZY_TOOLS"] = "0"
        _ok("lazy_enabled() reads the env toggle", lazy_enabled() is False, state)
        resp2 = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        _ok("BOTTE_MCP_LAZY_TOOLS=0 restores the full catalog",
            len(resp2["result"]["tools"]) == len(TOOLS), state)
    finally:
        if saved is None:
            os.environ.pop("BOTTE_MCP_LAZY_TOOLS", None)
        else:
            os.environ["BOTTE_MCP_LAZY_TOOLS"] = saved

    # protocol-level: find_tool is callable via tools/call
    call = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "find_tool", "arguments": {"query": "cluster status"}}})
    payload = json.loads(call["result"]["content"][0]["text"])
    _ok("find_tool works through tools/call and returns matches",
        len(payload["matches"]) > 0, state)

    # protocol-level: a NON-core tool is still callable by name even though it
    # isn't in the lazy listing — lazy only hides the catalog, not execution.
    non_core = next(n for n in DISPATCH if n not in CORE_TOOL_NAMES and n != "find_tool")
    _ok(f"non-core tool '{non_core}' is dispatchable despite not being listed",
        non_core in DISPATCH, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
