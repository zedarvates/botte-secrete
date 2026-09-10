"""Study provenance, sampling and no-dispatch contracts; no real model in CI."""
import argparse
import copy
from dataclasses import asdict
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from . import needle2_study as study
from .base import ToolRouteResult
from .memory_pilot import memory_tools


def row(case, route):
    return {"id": case["id"], "kind": case["kind"], "positive": case["expected_tool"] is not None,
            "route": asdict(route), "tool_correct": route.tool_name == case["expected_tool"],
            "call_correct": route.tool_name == case["expected_tool"] and route.arguments == case["expected_arguments"],
            "abstained": route.abstained, "runtime_error": False, "latency_ms": 1.0}


def config(url="http://127.0.0.1:1234"):
    return {"base_url": url, "model": "fixture-model", "weights_sha256": "a" * 64,
            "quantization": "fixture", "runtime_version": "fixture"}


@pytest.mark.parametrize("text", [
    '{"tool_name":"memory_forget","arguments":{"key":"demo"}}',
    '{"tool_name":"memory_history","arguments":{"key":"../../secret"}}',
    '{"tool_name":"memory_history","arguments":{}}',
    '{"tool_name":"memory_wiki","arguments":{"project_id":"other"}}',
    '{"tool_name":"memory_scribe","arguments":{"text":"hello","actor_id":"admin"}}',
    '{"tool_name":null,"arguments":{"query":"hello"}}',
    '{"tool_name":"memory_wiki","arguments":{},"execute":true}',
    '```json\n{"tool_name":"memory_wiki","arguments":{}}\n```',
])
def test_rejects_invalid_generalist_proposals_without_repairs(text):
    result = study.generalist_route(text)
    assert result.abstained and not result.executable


def test_generalist_exact_argument_and_empty_query_not_normalized():
    r = study.generalist_route('{"tool_name":"memory_scribe","arguments":{"text":"État exact"}}')
    assert r.arguments == {"text": "État exact"} and not r.executable
    r = study.generalist_route('{"tool_name":"memory_wiki","arguments":{"query":""}}')
    assert r.arguments == {"query": ""}


@pytest.mark.parametrize("url", ["https://example.com", "http://8.8.8.8", "http://169.254.169.254",
    "http://user:secret@127.0.0.1", "http://127.0.0.1/other", "http://127.0.0.1?key=secret", "file:///tmp/a"])
def test_public_metadata_or_credential_urls_are_rejected(url):
    with pytest.raises((ValueError, TypeError)):
        study.Generalist(config(url))


def test_real_http_fixture_records_one_request_no_tool_dispatch():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            result = {"model": "fixture-model", "choices": [{"finish_reason": "stop",
                      "message": {"content": '{"tool_name":"memory_wiki","arguments":{}}'}}]}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        router = study.Generalist(config(f"http://127.0.0.1:{server.server_port}"))
        result = router.route("Affiche le wiki", memory_tools())
        assert not result.executable and result.tool_name == "memory_wiki"
        assert len(requests) == 1 and requests[0]["temperature"] == 0
        assert requests[0]["max_tokens"] == 256 and "tools" not in requests[0]
        assert len(router.last["response_sha256"]) == 64
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_redirect_cannot_forward_credentials():
    with pytest.raises(ValueError, match="redirect"):
        study.NoRedirect().redirect_request(None, None, 307, None, None, "http://8.8.8.8")


def test_protocol_and_splits_are_source_bound(tmp_path):
    protocol, _, splits = study.load_protocol()
    assert all(len(cases) == 20 for cases in splits.values())
    changed = copy.deepcopy(protocol)
    changed["splits"]["calibration"]["sha256"] = "0" * 64
    target = tmp_path / "bad.json"
    study.write_json(target, changed)
    with pytest.raises(ValueError, match="dataset changed"):
        study.load_protocol(target)
    changed = copy.deepcopy(protocol)
    changed["source_sha256"]["skills/tool_router/needle2_study.py"] = "0" * 64
    target2 = tmp_path / "source-bad.json"
    study.write_json(target2, changed)
    with pytest.raises(ValueError, match="source changed"):
        study.load_protocol(target2)


def test_denominators_include_wrong_positive_proposals():
    p = {"id": "p", "kind": "positive", "expected_tool": "memory_wiki", "expected_arguments": {}}
    n = {"id": "n", "kind": "negative", "expected_tool": None, "expected_arguments": {}}
    rows = [row(p, ToolRouteResult("memory_wiki", {}, "needle", .8)),
            row(p, ToolRouteResult("memory_history", {"key": "x"}, "needle", .7)),
            row(n, ToolRouteResult("memory_wiki", {}, "needle", .6))]
    summary = study.summarize(rows)
    assert summary["exact_proposal_precision"] == 1 / 3
    assert summary["positive_wrong_proposals"] == summary["negative_proposals"] == 1
    assert summary["positive_exact_coverage"] == .5
    assert study.summarize(rows, .9)["exact_proposal_precision"] is None


def test_sparse_safe_threshold_does_not_open_validation():
    _, _, splits = study.load_protocol()
    rows = [row(c, ToolRouteResult(c["expected_tool"], c["expected_arguments"], "needle", .8))
            if c["expected_tool"] == "memory_history" else row(c, ToolRouteResult.abstain("needle", "model_abstained"))
            for c in splits["calibration"]]
    result = study.select({"backend": "needle", "split": "calibration", "cases": rows}, [0, .65, .9])
    assert result["decision"] == "stop_insufficient_safe_coverage"
    assert result["selected_threshold"] is None and result["best_diagnostic_threshold"] == .65
    assert not result["activation_allowed"]


def test_output_collision_and_unselected_validation_make_no_inference(tmp_path, monkeypatch):
    protocol, sha, splits = study.load_protocol()
    def forbidden(*args, **kwargs):
        pytest.fail("router must not initialize")
    monkeypatch.setattr(study, "Needle2ToolRouter", forbidden)
    output = tmp_path / "result.json"
    args = argparse.Namespace(output=output, split="validation", selection=None, calibration=None)
    with pytest.raises(ValueError, match="validation requires"):
        study.collect(args, protocol, sha, splits)
    output.with_suffix(".json.jsonl").write_text("partial\n", encoding="utf-8")
    with pytest.raises(ValueError, match="journal exists"):
        study.collect(args, protocol, sha, splits)


def test_checked_report_recomputes_labels_and_rejects_incomplete(tmp_path):
    protocol, sha, splits = study.load_protocol()
    report = {"schema_version": "botte.needle2-study-run/v1", "protocol_sha256": sha, "split": "calibration",
              "dataset_sha256": protocol["splits"]["calibration"]["sha256"], "complete": True,
              "cases": [row(c, ToolRouteResult.abstain("needle", "model_abstained")) for c in splits["calibration"]],
              **study.BOUNDARY}
    report["cases"][0]["call_correct"] = True
    path = tmp_path / "wrong-label.json"
    study.write_json(path, report)
    with pytest.raises(ValueError, match="scoring"):
        study.checked_report(path, protocol, sha, splits)
    report["complete"] = False
    path = tmp_path / "incomplete.json"
    study.write_json(path, report)
    with pytest.raises(ValueError, match="incomplete"):
        study.checked_report(path, protocol, sha, splits)


def test_absent_generalist_remains_unmeasured_and_mismatch_rejected():
    needle = {"backend": "needle", "split": "calibration", "protocol_sha256": "a",
              "dataset_sha256": "b", "selection_sha256": None, "cases": []}
    summary = study.compare(needle, None)
    assert summary["generalist"] == "not_measured"
    assert not summary["paired_comparison_measured"] and not summary["activation_allowed"]
    with pytest.raises(ValueError, match="identical"):
        study.compare(needle, {**needle, "backend": "generalist", "dataset_sha256": "different"})
