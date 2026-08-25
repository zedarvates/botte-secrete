#!/usr/bin/env python3
"""Tests for lazy tool loading — the ToolSearch pattern on our own MCP server.

    python -m skills.llm_mcp.test_lazy
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
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
    qa_matches = [item["name"] for item in find_tool("quality knn advice", TOOLS)["matches"]]
    _ok("quality-language discovery surfaces qa_advise",
        "qa_advise" in qa_matches, state)

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

    from skills.botte_nn import active_learning as al_mod
    old_data_dir = al_mod.DATA_DIR
    with tempfile.TemporaryDirectory() as temp_dir:
        al_mod.DATA_DIR = Path(temp_dir) / "active_learning"
        try:
            feedback_id = al_mod.record_observation(
                "binary_router", [0.2, 1.0, 1.0], 0, "local_returned")
            feedback_call = handle({
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "route_feedback", "arguments": {
                    "feedback_id": feedback_id, "correct_route": "cloud"}}})
            feedback_payload = json.loads(
                feedback_call["result"]["content"][0]["text"])
            _ok("route_feedback verifies an auto_route observation through MCP",
                feedback_payload["verified"] is True
                and feedback_payload["feedback_id"] == feedback_id, state)
        finally:
            al_mod.DATA_DIR = old_data_dir

    with tempfile.TemporaryDirectory() as qa_project:
        qa_record_call = handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "qa_record", "arguments": {
                "task": "summarize a verified parser test",
                "project": qa_project,
                "route": "local",
                "verdict": "PASS",
                "verified_by": "tests:pytest",
                "evidence_refs": ["pytest:test_parser"],
            }},
        })
        qa_record = json.loads(qa_record_call["result"]["content"][0]["text"])
        _ok("qa_record persists a verified outcome through MCP",
            qa_record["verified"] is True and qa_record["raw_task_stored"] is False,
            state)

        qa_advice_call = handle({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "qa_advise", "arguments": {
                "task": "deploy the parser fix", "project": qa_project,
                "risk": "high",
            }},
        })
        qa_advice = json.loads(qa_advice_call["result"]["content"][0]["text"])
        _ok("qa_advise preserves the human gate through MCP",
            qa_advice["status"] == "gated" and qa_advice["acted"] is False,
            state)

        qa_status_call = handle({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "qa_status", "arguments": {"project": qa_project}},
        })
        qa_status = json.loads(qa_status_call["result"]["content"][0]["text"])
        _ok("qa_status exposes maturity through MCP",
            qa_status["verified_samples"] == 1 and qa_status["mode"] == "shadow",
            state)

    # protocol-level: a NON-core tool is still callable by name even though it
    # isn't in the lazy listing — lazy only hides the catalog, not execution.
    non_core = next(n for n in DISPATCH if n not in CORE_TOOL_NAMES and n != "find_tool")
    _ok(f"non-core tool '{non_core}' is dispatchable despite not being listed",
        non_core in DISPATCH, state)

    # TOOLS and DISPATCH must stay in lockstep — a tool declared but not wired
    # (or wired but not declared) is a silent capability gap.
    _ok("every declared tool has a dispatch handler and vice versa",
        real_names == set(DISPATCH), state)

    # v1.7.0 tools wired into the MCP server (audit P1): bench_run/doctor/
    # fleet_status existed in TOOLS but had no DISPATCH entry; compress/
    # shape_query/belt2_hint expose universal_compressor/token_shaper/Belt 2.0
    # which were otherwise unreachable from the harness.
    for name, args in (
        ("bench_run", {}),
        ("doctor", {"project": "."}),
        ("fleet_status", {}),
        ("compress", {"content": "aaa bbb aaa bbb aaa bbb " * 10}),
        ("shape_query", {"query": "fix a typo"}),
        ("belt2_hint", {"text": "audit this repo"}),
    ):
        r = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": args}})
        ok = r is not None and not r["result"].get("isError")
        _ok(f"'{name}' tool call succeeds", ok, state)

    # Memory Hub is exercised through the real server dispatch while its
    # durable state is redirected to a temporary directory. This catches
    # schema/dispatch drift without writing to ~/.botte during tests.
    saved_hub_dir = os.environ.get("BOTTE_MEMORY_HUB_DIR")
    try:
        with tempfile.TemporaryDirectory() as hub_dir:
            os.environ["BOTTE_MEMORY_HUB_DIR"] = hub_dir

            def hub_call(name, arguments):
                response = handle({
                    "jsonrpc": "2.0", "id": 10, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                })
                text = response["result"]["content"][0]["text"]
                payload = None if response["result"].get("isError") else json.loads(text)
                return response, payload

            _, proposed = hub_call("propose_memory", {
                "project_id": "lazy_test", "key": "decision:one",
                "value": "keep local", "agent_id": "alice",
                "visibility": "project",
            })
            _ok("'propose_memory' works through tools/call",
                proposed["status"] == "proposal", state)

            _, review = hub_call("promote_memory", {
                "project_id": "lazy_test", "key": "decision:one",
                "new_status": "review_active", "actor_id": "reviewer",
            })
            _, promoted = hub_call("promote_memory", {
                "project_id": "lazy_test", "key": "decision:one",
                "new_status": "promoted", "actor_id": "reviewer",
            })
            _ok("memory lifecycle is dispatchable",
                review["success"] and promoted["success"], state)

            _, bundle = hub_call("context_bundle", {
                "project_id": "lazy_test", "agent_id": "builder",
            })
            _ok("promoted memory reaches context_bundle",
                [item["key"] for item in bundle["entries"]] == ["decision:one"], state)

            denied, _ = hub_call("forget_memory", {
                "project_id": "lazy_test", "key": "decision:one", "actor_id": "bob",
            })
            _ok("non-owner cannot forget memory",
                denied["result"].get("isError") is True, state)

            _, forgotten = hub_call("forget_memory", {
                "project_id": "lazy_test", "key": "decision:one", "actor_id": "alice",
            })
            _ok("owner can forget memory", forgotten["deleted"] is True, state)
    finally:
        if saved_hub_dir is None:
            os.environ.pop("BOTTE_MEMORY_HUB_DIR", None)
        else:
            os.environ["BOTTE_MEMORY_HUB_DIR"] = saved_hub_dir

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
