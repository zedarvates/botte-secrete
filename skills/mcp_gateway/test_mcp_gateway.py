#!/usr/bin/env python3
"""Tests for mcp_gateway — registry, server, dispatcher.

    python -m skills.mcp_gateway.test_mcp_gateway
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.mcp_gateway.registry import discover_skills, SkillTool, load_config
from skills.mcp_gateway.server import MCPServer, _build_tool_definitions
from skills.mcp_gateway.dispatcher import Dispatcher


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== mcp_gateway tests ==")

    # ── Registry ──
    skills = discover_skills()
    _ok("discover_skills returns list", isinstance(skills, list), state)
    _ok("discover at least 3 skills", len(skills) >= 3, state)

    # Check specific skills
    names = [s.name for s in skills]
    _ok("security_scanner discovered", "security_scanner" in names, state)
    _ok("fast_context discovered", "fast_context" in names, state)
    _ok("meta_harness discovered", "meta_harness" in names, state)
    _ok("botte_nn discovered", "botte_nn" in names, state)

    # Check SkillTool attributes
    for s in skills[:3]:
        _ok(f"{s.name}: has name", len(s.name) > 0, state)
        _ok(f"{s.name}: has description", len(s.description) > 0, state)
        _ok(f"{s.name}: has module_path", len(s.module_path) > 0, state)
        _ok(f"{s.name}: enabled by default", s.enabled, state)

    # ── Config ──
    config = load_config()
    _ok("load_config returns dict", isinstance(config, dict), state)
    _ok("config has enabled_skills key", "enabled_skills" in config, state)
    _ok("config has excluded_skills key", "excluded_skills" in config, state)

    # ── Tool definitions ──
    tools = _build_tool_definitions(skills[:5])
    _ok("build_tool_definitions returns list", isinstance(tools, list), state)
    _ok("tool defs have name/description/inputSchema",
        all("name" in t and "description" in t and "inputSchema" in t for t in tools),
        state)
    _ok("tool defs have valid JSON Schema",
        all(t["inputSchema"]["type"] == "object" for t in tools), state)

    # ── MCPServer ──
    server = MCPServer()
    _ok("MCPServer initializes", isinstance(server, MCPServer), state)
    _ok("MCPServer has tools", len(server.tools) > 0, state)

    # ── JSON-RPC handlers ──

    # Initialize
    resp = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}
    })
    _ok("initialize returns protocolVersion",
        resp and resp.get("result", {}).get("protocolVersion") == "2024-11-05",
        state)
    _ok("initialize returns serverInfo",
        resp and resp["result"].get("serverInfo", {}).get("name") == "botte-gateway",
        state)

    # tools/list
    resp = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list"
    })
    _ok("tools/list returns tools array",
        resp and "tools" in resp.get("result", {}), state)
    _ok("tools/list has at least 3 tools",
        resp and len(resp["result"]["tools"]) >= 3, state)

    # tools/call — nonexistent tool
    resp = server.handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    })
    _ok("nonexistent tool returns error",
        resp and "error" in resp, state)

    # tools/call — botte_nn (fast, no subprocess)
    resp = server.handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {
            "name": "botte_nn",
            "arguments": {
                "model": "effort_classifier",
                "input": [0.1, 0.2, 0.8, 0.0],
            },
        },
    })
    _ok("botte_nn call returns result",
        resp and "result" in resp, state)
    if "result" in resp:
        _ok("botte_nn result has content",
            "content" in resp["result"], state)

    # tools/call — security_scanner scan self
    resp = server.handle({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {
            "name": "security_scanner",
            "arguments": {"root": ".", "fail_on": "critical"},
        },
    })
    _ok("security_scanner call returns result",
        resp and "result" in resp, state)

    # Notification
    resp = server.handle({
        "jsonrpc": "2.0", "method": "notifications/initialized",
    })
    _ok("notifications return None", resp is None, state)

    # Unknown method
    resp = server.handle({
        "jsonrpc": "2.0", "id": 99, "method": "unknown_method"
    })
    _ok("unknown method returns error",
        resp and "error" in resp, state)

    # ── Dispatcher ──
    d = Dispatcher()
    call_result = d._ok("test output")
    _ok("dispatcher._ok returns content",
        "content" in call_result, state)
    err_result = d._error("test error")
    _ok("dispatcher._error has isError",
        err_result.get("isError") is True, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
