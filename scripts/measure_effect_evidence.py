"""Compare full evidence with targeted reads on two explicitly synthetic runs."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skills.capabilities.effects import contract_template
from skills.capabilities.observations import digest, empty_report, validate_report
from skills.capabilities.review import METHOD
from skills.llm_mcp.server import TOOLS, handle


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def fixture(writes, contract):
    """Fabricate bounded, schema-valid records, not evidence of real work."""
    report = empty_report("1" * 32)
    report["context"] = {"started_at": "2026-09-13T00:00:00+00:00", "cwd": "/fixture", "python": "3.12"}
    report["process"] = {"status": "exited", "exit_code": 0}
    report["problems"] = ["Synthetic serialization fixture; no described operation was executed."]
    ref = digest(contract)
    report["declarations"][ref] = contract
    parent = {"id": "c1", "parent_id": None, "capability_id": contract["capability_id"],
              "source_path": "/fixture/worker", "operation": "fixture parent", "context": {},
              "status": "returned", "duration_ms": 1, "declaration_status": "declared", "declaration_ref": ref}
    report["calls"].append(parent)
    for i in range(writes):
        failed = i == writes - 1
        call_id = f"c{i + 2}"
        report["calls"].append({**parent, "id": call_id, "parent_id": "c1", "operation": "fixture write",
                                "status": "raised" if failed else "returned"})
        report["observations"].append({"id": f"o{i + 1}", "call_id": call_id,
            "resource": f"/fixture/item-{i}.txt", "effect_ref": "/expected_effects/0",
            "facet": "file_present_after_write", "write_status": "raised" if failed else "returned",
            "before": {"state": "missing", "sha256": None, "size": None},
            "after": {"state": "present", "sha256": "2" * 64, "size": 7},
            "comparison": "deviation" if failed else "supported"})
    target = {"id": "t1", "scheme": "http", "address_kind": "loopback"}
    report["network"].append({"id": "n1", "call_id": "c1", "transport": "http", "method": "POST",
        "target": target, "effect_ref": "/expected_effects/0", "facet": "transport_response",
        "status": "returned", "http_status": 202, "response_target": target, "origin_changed": False,
        "response_complete": True, "duration_ms": 1, "error_kind": None,
        "comparison": "supported", "remote_effects": "unknown"})
    errors = validate_report(report)
    if errors:
        raise ValueError(errors)
    return report


def execution_measure(report, source, method_bytes, schema_bytes):
    """Read overview, then follow its reference and the resulting record index."""
    document = {"goal": "Synthetic multi-step execution", "mode": "safe_only",
                "summary": {"ran": 1, "failed": 1, "blocked": 1, "skipped": 0},
                "results": [{"capability": "worker", "command": "fixture write and POST",
                             "status": "ran", "exit_code": 0, "effects_observed": report},
                            {"capability": "worker", "command": "fixture failed step",
                             "status": "failed", "exit_code": 1},
                            {"capability": "worker", "command": "fixture gated step",
                             "status": "blocked", "exit_code": None}]}
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    args = {"source": source.as_posix(), "overview": True}
    exchanges = 0
    overview_exchange = 0
    reference = None
    for number, status in enumerate(("overview", "indexed", "selected"), 1):
        request = {"jsonrpc": "2.0", "id": number, "method": "tools/call",
                   "params": {"name": "effect_evidence", "arguments": args}}
        response = handle(request)
        if response.get("error") or response["result"].get("isError"):
            raise ValueError("execution overview read failed during measurement")
        view = json.loads(response["result"]["content"][0]["text"])
        if view["selection_status"] != status:
            raise ValueError("execution report changed or became unavailable")
        exchanges += size(request) + size(response)
        if status == "overview":
            overview_exchange = exchanges
            reference = view["results"][0]["review_after"]["evidence_ref"]
            args = reference
        elif status == "indexed":
            index = view["index"]
            args = {**reference, "selectors": [
                "/observations/" + index["observations"]["deviation"][0],
                "/network/" + index["network"]["returned"][0],
                "/declarations/" + index["declarations"][0]]}
    full = size(document) + method_bytes
    total = exchanges + schema_bytes + method_bytes
    return {"results": len(document["results"]), "full_execution_bytes": size(document),
            "full_with_method_bytes": full, "calls": 3,
            "overview_exchange_bytes": overview_exchange,
            "overview_with_method_bytes": overview_exchange + schema_bytes + method_bytes,
            "request_response_bytes": exchanges, "with_selected_details_bytes": total,
            "with_details_reduction_percent": round(100 * (1 - total / full), 1)}


def measure():
    method_bytes = len((ROOT / METHOD).read_bytes())
    definition = next(tool for tool in TOOLS if tool["name"] == "effect_evidence")
    rows = []
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as temp:
        try:
            os.chdir(temp)
            skill = Path("worker")
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: worker\ndescription: Synthetic fixture.\n---\n", encoding="utf-8")
            contract = contract_template(skill, "measurement/fixture:skills/worker")
            source = Path(".botte/reports/fixture.json")
            source.parent.mkdir(parents=True)
            for count in (2, 64):
                report = fixture(count, contract)
                source.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
                exchanges = 0
                expected = None
                for i, selectors in enumerate((None, [f"/observations/o{count}", "/network/n1",
                                                       f"/declarations/{digest(contract)}"]), 1):
                    args = {"source": source.as_posix()}
                    if selectors is not None:
                        args.update(selectors=selectors, expected_sha256=expected)
                    request = {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                               "params": {"name": "effect_evidence", "arguments": args}}
                    response = handle(request)
                    if response.get("error") or response["result"].get("isError"):
                        raise ValueError("evidence read failed during measurement")
                    view = json.loads(response["result"]["content"][0]["text"])
                    if view["selection_status"] != ("indexed" if selectors is None else "selected"):
                        raise ValueError("evidence became unavailable during measurement")
                    expected = view["evidence_sha256"]
                    exchanges += size(request) + size(response)
                full = size(report) + method_bytes
                targeted = size(definition) + exchanges + method_bytes
                rows.append({"synthetic_writes": count, "full_companion_bytes": size(report),
                             "full_with_method_bytes": full, "calls": 2, "tool_schema_bytes": size(definition),
                             "request_response_bytes": exchanges, "targeted_with_method_bytes": targeted,
                             "reduction_percent": round(100 * (1 - targeted / full), 1),
                             "execution_overview": execution_measure(report, source, method_bytes, size(definition))})
        finally:
            os.chdir(previous)
    return {"measurement": "UTF-8 serialized context; shared method included once in both paths",
            "method_bytes": method_bytes, "examples": rows,
            "limits": "Two synthetic companions and execution wrappers, read via real in-process MCP dispatch. Targeted cost includes index, selected write/network/declaration, linked calls, run limits, requests/responses and tool schema. Execution comparison also includes the initial overview. Full baselines are raw JSON without retrieval overhead. No real workflow, model tokens, quality or runtime savings measured; further reads add cost."}


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
