"""Needle 2 boundary tests. Fake engines test wiring, not model quality."""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from skills.memory_hub.shared_contract import READ_ONLY, SCHEMAS, validate
from skills.memory_hub.shared_mcp import MCPBridge
from skills.memory_hub.shared_service import MemoryService, Principal, RIGHTS, ServiceError
from skills.memory_hub.store import MemoryStore
from skills.tool_router.base import ToolRouteResult
from skills.tool_router.memory_pilot import memory_call, memory_tools, propose
from skills.tool_router.needle2_adapter import Needle2ToolRouter, parse_response
from skills.tool_router.needle2_cli import evaluate, main


def answer(name="memory_history", args=None, confidence=.95, **extra):
    return {"type": "call", "success": True, "error": None, "error_code": None,
            "function_calls": [{"name": name, "arguments": {"key": "demo"} if args is None else args}],
            "confidence": confidence, **extra}


def test_accepted_proposal_never_becomes_executable():
    route = parse_response(answer(), memory_tools())
    assert route.tool_name == "memory_history"
    assert route.arguments == {"key": "demo"}
    assert not route.executable
    assert route.reason == "advisory_only"


@pytest.mark.parametrize("confidence", [None, True, "0.99", float("nan"), float("inf"), -1, 1.1, .89])
def test_bad_or_low_confidence_abstains(confidence):
    assert parse_response(answer(confidence=confidence), memory_tools()).abstained


@pytest.mark.parametrize("payload", [
    [], {}, answer(success=False), answer(error_code="failed"),
    answer(type="respond"), answer(function_calls=[]),
    answer(function_calls=[{}, {}]), answer(function_calls=["bad"]),
    answer(name="memory_forget"), answer(args={"key": "../../secret"}),
    answer(args={"key": "demo", "project_id": "other"}),
    answer(args={"key": "demo", "actor_id": "operator"}),
    answer(args={}), answer(args={"key": 3}), answer(args={"key": ""}),
    answer(validation={"ungrounded": ["memory_history.key"]}),
    answer(validation={"ungrounded": [], "negation": True}),
    answer(validation="bad"), answer(function_calls=[{"name": "memory_history", "arguments": {"key": "demo"}, "execute": True}]),
])
def test_invalid_model_outputs_abstain(payload):
    assert parse_response(payload, memory_tools()).abstained


def test_missing_library_never_imports_engine_or_downloads(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("no process should be started")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    router = Needle2ToolRouter()
    assert router.route("wiki", memory_tools()).reason == "needle2_library_missing"
    assert router.route("", memory_tools()).reason == "empty_query"
    assert router.route("é" * 300, memory_tools()).reason == "input_too_large"
    assert router.route("wiki", memory_tools() * 2).reason == "invalid_tool_catalog"


@pytest.mark.parametrize("tool,args,operation", [
    ("memory_context", {"query": "GPU"}, "recall"),
    ("memory_observations", {"query": "CI"}, "recall"),
    ("memory_history", {"key": "demo"}, "history"),
    ("memory_wiki", {}, "wiki"),
    ("memory_scribe", {"text": "GPU"}, "scribe"),
])
def test_all_five_tools_map_to_existing_read_contract(tool, args, operation):
    route = parse_response(answer(tool, args), memory_tools())
    call = memory_call(route, "pilot")
    assert call["name"] == "memory_" + operation
    assert operation in READ_ONLY
    validate(SCHEMAS[operation], call["arguments"])
    assert call["arguments"]["project_id"] == "pilot"
    if tool == "memory_observations":
        assert call["arguments"]["area"] == "observations"
    if operation == "scribe":
        assert call["arguments"]["record"]["source"]["type"] == "generated"


def test_revalidation_rejects_forged_proposal_and_project():
    with pytest.raises(ValueError):
        memory_call(ToolRouteResult("memory_forget", {"key": "demo"}), "pilot")
    with pytest.raises(ValueError):
        memory_call(ToolRouteResult("memory_context", {"project_id": "other"}), "pilot")
    with pytest.raises(ValueError):
        memory_call(ToolRouteResult(), "../pilot")


def test_mapping_through_real_mcp_preserves_memory_and_identity(tmp_path):
    service = MemoryService(tmp_path / "hub")
    principal = Principal("operator", frozenset({"pilot"}), RIGHTS)
    data = {"text": "Synthetic GPU decision", "kind": "fact", "visibility": "private",
            "source": {"type": "user", "id": "synthetic", "run_id": "test",
                       "observed_at": time.time() - 10, "excerpt": "Synthetic GPU decision"}}
    service.call("capture", {"project_id": "pilot", "key": "demo", "request_id": "capture", "record": data}, principal)
    for version, status in enumerate(("review_active", "promoted"), start=1):
        service.call("review", {"project_id": "pilot", "key": "demo", "request_id": status,
                               "expected_version": version, "new_status": status}, principal)
    seen = []
    class Client:
        def call(self, operation, arguments):
            assert operation in READ_ONLY
            seen.append(operation)
            return service.call(operation, arguments, principal)
    bridge = MCPBridge(Client())
    bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    def snapshot():
        with MemoryStore(service.base_dir) as store:
            return list(store._conn("pilot").iterdump())
    before = snapshot()
    for name, args in [("memory_context", {}), ("memory_observations", {}),
                       ("memory_history", {"key": "demo"}), ("memory_wiki", {}),
                       ("memory_scribe", {"text": "GPU"})]:
        route = parse_response(answer(name, args), memory_tools())
        response = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": memory_call(route, "pilot")})
        assert not response["result"]["isError"]
    assert snapshot() == before
    assert seen == ["recall", "recall", "history", "wiki", "scribe"]
    other = Principal("other", frozenset({"pilot"}), frozenset({"read"}))
    call = memory_call(parse_response(answer("memory_context", {}), memory_tools()), "pilot")
    assert service.call("recall", call["arguments"], other)["entries"] == []
    with pytest.raises(ServiceError):
        service.call("recall", {"project_id": "forbidden"}, other)


def test_propose_does_not_dispatch_any_memory_operation():
    class Router:
        def route(self, query, tools):
            return parse_response(answer("memory_context", {}), tools)
    result = propose("recall", Router(), "pilot")
    assert result["memory_call"]["name"] == "memory_recall"
    assert not result["executed"] and not result["activation_allowed"]
    assert result["effects"] == {"memory_writes": 0, "tool_calls_executed": 0}


def test_benchmark_joint_accuracy_and_negative_denominator(tmp_path):
    cases = [
        {"id": "yes", "kind": "positive", "query": "yes", "expected_tool": "memory_context", "expected_arguments": {}},
        {"id": "no", "kind": "negative", "query": "no", "expected_tool": None, "expected_arguments": {}},
    ]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    class WrongRouter:
        def route(self, *_):
            return ToolRouteResult("memory_wiki", {})
    result = evaluate(WrongRouter(), path)
    assert result["positive_exact_call_accuracy"] == 0
    assert result["negative_abstention_accuracy"] == 0
    assert result["false_proposals_on_negative_cases"] == 1


def test_cli_unavailable_is_nonzero_without_claiming_model_evaluation(capsys):
    assert main(["route", "wiki", "--project-id", "pilot"]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["route"]["reason"] == "needle2_library_missing"
    assert result["memory_call"] is None and not result["executed"]


def test_worker_resets_each_request_and_disables_network_telemetry(tmp_path, monkeypatch):
    # Exercise the actual worker loop with a stand-in module: model quality is
    # intentionally excluded, but accidental .run() execution is detectable.
    from io import BytesIO
    from types import SimpleNamespace
    from skills.tool_router import needle2_worker
    events = []
    class Engine:
        def __init__(self, tools):
            import os
            assert os.environ["NEEDLE_TELEMETRY"] == "0"
            assert os.environ["HF_HUB_OFFLINE"] == "1"
            events.append("init")
        def reset(self): events.append("reset")
        def complete(self, text, **kw):
            events.append(text)
            return answer()
        def close(self): events.append("close")
        def run(self, *_): pytest.fail("must not execute tools")
    monkeypatch.setattr(needle2_worker.importlib.metadata, "version", lambda _: "2.0.13")
    monkeypatch.setitem(sys.modules, "needle", SimpleNamespace(Needle=Engine))
    monkeypatch.setattr(sys, "argv", ["worker", "--library", str(tmp_path / "lib")])
    payload = b'{"tools":[]}\n{"query":"one"}\n{"query":"two"}\n'
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=BytesIO(payload)))
    assert needle2_worker.main() == 0
    assert events == ["init", "reset", "one", "reset", "two", "close"]


@pytest.mark.parametrize("mode,reason", [
    ("blocked_init", "needle2_timeout"),
    ("blocked_inference", "needle2_timeout"),
    ("malformed", "needle2_runtime_error"),
    ("oversized", "needle2_runtime_error"),
    ("crash", "needle2_runtime_error"),
])
def test_child_failure_is_bounded_and_worker_is_reaped(tmp_path, monkeypatch, mode, reason):
    # Real process/pipe lifecycle with a stand-in engine, including a child
    # that never consumes the full initialization message.
    from dataclasses import replace
    original_popen = subprocess.Popen
    children = []
    script = """
import json, sys, time
mode = sys.argv[1]
if mode == 'blocked_init': time.sleep(10)
json.loads(sys.stdin.readline())
print('{"ready":true}', flush=True)
sys.stdin.readline()
if mode == 'blocked_inference': time.sleep(10)
if mode == 'malformed': print('not json', flush=True)
if mode == 'oversized': print('x' * 70000, flush=True)
"""
    def spawn(_command, **kwargs):
        child = original_popen([sys.executable, "-u", "-c", script, mode], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, "Popen", spawn)
    library = tmp_path / "stand-in-library"
    library.write_bytes(b"not a native model")
    tools = memory_tools()
    if mode == "blocked_init":
        tools = (replace(tools[0], description="x" * 14000),)
    with Needle2ToolRouter(library, timeout=.5) as router:
        started = time.monotonic()
        result = router.route("wiki", tools)
        assert time.monotonic() - started < 5
        assert result.reason == reason and not result.executable
        assert router._process is None
    assert len(children) == 1 and children[0].poll() is not None


def test_two_routers_use_separate_workers_and_close_them(tmp_path, monkeypatch):
    original_popen = subprocess.Popen
    children = []
    script = """
import json, sys
catalog = json.loads(sys.stdin.readline())['tools']
# Regression: sorting schema fields changed real Needle 2 selections.
assert all(list(tool) == ['name', 'description', 'parameters'] for tool in catalog)
print('{"ready":true}', flush=True)
for line in sys.stdin:
    query = json.loads(line)['query']
    print(json.dumps({'success': True, 'type': 'call', 'confidence': .99,
          'function_calls': [{'name': 'memory_history', 'arguments': {'key': query}}]}), flush=True)
"""
    def spawn(_command, **kwargs):
        child = original_popen([sys.executable, "-u", "-c", script], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, "Popen", spawn)
    library = tmp_path / "stand-in-library"
    library.write_bytes(b"not a native model")
    with Needle2ToolRouter(library) as first, Needle2ToolRouter(library) as second:
        assert first.route("one", memory_tools()).arguments == {"key": "one"}
        assert second.route("two", memory_tools()).arguments == {"key": "two"}
        assert first.route("three", memory_tools()).arguments == {"key": "three"}
        assert children[0].pid != children[1].pid
    assert len(children) == 2 and all(child.poll() is not None for child in children)
