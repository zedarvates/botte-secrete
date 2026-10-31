"""Offline regression corpus for advisory assessment, never a model-selection score."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from skills.atomic_json import write_json
from skills.preflight.assessment import assess_task
from skills.console_utf8 import force_utf8

CORPUS = Path(__file__).with_name("evaluation_cases.json")
MAX_CORPUS_BYTES = 262_144
_INTENTS = {"statistics", "file_duplicates", "local_links", "github_research",
            "software_testing", "game_playtest", "code_work", "content_transform", "read_analysis"}
_EXPECT_KEYS = {"status", "intent", "candidate_tool", "no_candidate_tools",
                "forbidden_intents", "forbidden_candidate_tools", "reasons_include",
                "missing_prerequisites_include"}
_TOOL_NAME = re.compile(r"[A-Za-z0-9_.:/-]{1,160}\Z")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strings(value: object) -> bool:
    return (isinstance(value, list) and len(value) <= 64
            and all(isinstance(item, str) and 0 < len(item) <= 2048 for item in value)
            and len(set(value)) == len(value))


def validate_corpus(corpus: dict) -> None:
    """Reject typos and ineffective expectations before running any assessment."""
    if not isinstance(corpus, dict) or set(corpus) != {
            "schema", "baseline_source_revision", "notes", "tool_inventories", "cases"}:
        raise ValueError("invalid corpus fields")
    if corpus["schema"] != "parcimonia.assessment-corpus/v1":
        raise ValueError("unsupported corpus schema")
    if (not isinstance(corpus["baseline_source_revision"], str)
            or not re.fullmatch(r"[a-f0-9]{40}", corpus["baseline_source_revision"])
            or not _strings(corpus["notes"])):
        raise ValueError("invalid corpus provenance or notes")
    if len(_canonical(corpus)) > MAX_CORPUS_BYTES:
        raise ValueError("corpus exceeds byte limit")
    inventories = corpus["tool_inventories"]
    if not isinstance(inventories, dict) or "default" not in inventories or len(inventories) > 32:
        raise ValueError("invalid tool inventories")
    for name, tools in inventories.items():
        if not isinstance(name, str) or not name:
            raise ValueError("invalid inventory name")
        if tools is None:
            continue
        if not isinstance(tools, list) or len(tools) > 64:
            raise ValueError("invalid inventory")
        names = set()
        for tool in tools:
            if not isinstance(tool, dict) or set(tool) - {"name", "description"} or "name" not in tool:
                raise ValueError("invalid tool metadata")
            tool_name, description = tool["name"], tool.get("description", "")
            if (not isinstance(tool_name, str) or not _TOOL_NAME.fullmatch(tool_name)
                    or tool_name in names or not isinstance(description, str)
                    or len(description.encode("utf-8")) > 2048):
                raise ValueError("invalid tool metadata")
            names.add(tool_name)
    cases = corpus["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 128:
        raise ValueError("expected 1 to 128 cases")
    ids = set()
    for case in cases:
        required = {"id", "language", "group", "split", "task", "expect", "codex"}
        if not isinstance(case, dict) or not required <= set(case) or set(case) - required - {
                "tool_inventory", "context_budget"}:
            raise ValueError("invalid case fields")
        if not all(isinstance(case[key], str) and case[key].strip() for key in (
                "id", "language", "group", "split", "task")):
            raise ValueError("invalid case text")
        if case["id"] in ids or len(case["task"].encode("utf-8")) > 16_384:
            raise ValueError("duplicate case id or oversized task")
        ids.add(case["id"])
        inventory_name = case.get("tool_inventory", "default")
        if not isinstance(inventory_name, str) or inventory_name not in inventories:
            raise ValueError("unknown tool inventory")
        budget = case.get("context_budget", 2000)
        if type(budget) is not int or not 0 <= budget <= 16_000:
            raise ValueError("invalid context budget")
        expect = case["expect"]
        if not isinstance(expect, dict) or not expect or set(expect) - _EXPECT_KEYS:
            raise ValueError("unknown or empty expectation")
        if "intent" in expect and expect["intent"] is not None and (
                not isinstance(expect["intent"], str) or expect["intent"] not in _INTENTS):
            raise ValueError("unknown expected intent")
        if "status" in expect and (not isinstance(expect["status"], str)
                or expect["status"] not in {"proposed", "abstained"}):
            raise ValueError("invalid expected status")
        if "no_candidate_tools" in expect and expect["no_candidate_tools"] is not True:
            raise ValueError("invalid no_candidate_tools")
        for key in ("forbidden_intents", "forbidden_candidate_tools", "reasons_include", "missing_prerequisites_include"):
            if key in expect and (not _strings(expect[key]) or not expect[key]):
                raise ValueError(f"invalid {key}")
        if set(expect.get("forbidden_intents", [])) - _INTENTS:
            raise ValueError("unknown forbidden intent")
        candidate = expect.get("candidate_tool")
        offered = inventories[inventory_name] or []
        if "candidate_tool" in expect and (not isinstance(candidate, str) or candidate not in {
                tool["name"] for tool in offered}):
            raise ValueError("expected candidate must be offered")
        if (candidate is not None and (expect.get("no_candidate_tools")
                or expect.get("status") == "abstained"
                or candidate in expect.get("forbidden_candidate_tools", []))
                or expect.get("intent") in expect.get("forbidden_intents", [])
                or expect.get("status") == "abstained" and expect.get("intent") is not None
                or expect.get("status") == "proposed" and "intent" in expect and expect["intent"] is None
                or "intent" in expect and expect["intent"] is None and candidate is not None):
            raise ValueError("contradictory expectations")
        codex = case["codex"]
        if (not isinstance(codex, dict) or set(codex) != {"action", "checks"}
                or not isinstance(codex["action"], str) or not codex["action"]
                or not _strings(codex["checks"])):
            raise ValueError("invalid future Codex criteria")


def load_corpus(path: str | Path | None = None) -> dict:
    with Path(path or CORPUS).open("rb") as handle:
        raw = handle.read(MAX_CORPUS_BYTES + 1)
    if len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("corpus exceeds byte limit")
    corpus = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    validate_corpus(corpus)
    return corpus


def grade_assessment(case: dict, assessment: dict, offered_tools: list[dict] | None) -> list[str]:
    """Check the shortlist, not executable capability or the model's final answer."""
    failures = []
    if not isinstance(assessment, dict):
        return ["assessment_not_object"]
    expect = case["expect"]
    intent = assessment.get("intent")
    status = assessment.get("status")
    if assessment.get("schema") != "parcimonia.task-assessment/v1":
        failures.append("assessment_schema")
    if not ((status == "abstained" and intent is None) or (
            status == "proposed" and isinstance(intent, str) and intent in _INTENTS)):
        failures.append("status_intent_inconsistent")
    for key in ("intent", "status"):
        if key in expect and assessment.get(key) != expect[key]:
            failures.append(f"expected_{key}")
    if intent in expect.get("forbidden_intents", []):
        failures.append("forbidden_intent")
    candidates = assessment.get("candidate_tools")
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        failures.append("invalid_candidates")
        candidates = []
    names = [item.get("name") for item in candidates]
    allowed = {tool["name"] for tool in offered_tools or []}
    if any(not isinstance(name, str) or name not in allowed for name in names):
        failures.append("unoffered_candidate")
    if len({name for name in names if isinstance(name, str)}) != len(names) or len(names) > 5:
        failures.append("duplicate_or_oversized_shortlist")
    if any(item.get("capability_verified") is not False for item in candidates):
        failures.append("unverified_capability_claim")
    if status == "abstained" and candidates:
        failures.append("candidate_after_abstention")
    if assessment.get("tool_selection_status") != ("proposed" if candidates else "abstained"):
        failures.append("shortlist_status_inconsistent")
    if expect.get("candidate_tool") and expect["candidate_tool"] not in names:
        failures.append("expected_candidate_absent")
    if expect.get("no_candidate_tools") and candidates:
        failures.append("expected_empty_shortlist")
    if any(name in expect.get("forbidden_candidate_tools", []) for name in names):
        failures.append("forbidden_candidate")
    for expected, observed in (("reasons_include", "reasons"),
                               ("missing_prerequisites_include", "missing_prerequisites")):
        actual = assessment.get(observed)
        if not _strings(actual) or any(item not in actual for item in expect.get(expected, [])):
            failures.append(f"invalid_or_missing_{observed}")
    boundaries = assessment.get("boundaries", {})
    required = {"execution": False, "network": False, "model_calls": 0,
                "authorization": "unknown", "risk": "unknown", "locality": "unknown",
                "real_time_capability": "unknown"}
    if not isinstance(boundaries, dict) or any(
            type(boundaries.get(key)) is not type(value) or boundaries.get(key) != value
            for key, value in required.items()):
        failures.append("advisory_boundaries_violated")
    usage = assessment.get("measured_usage")
    if not isinstance(usage, dict) or set(usage) != {"cloud_tokens", "latency_ms", "cost", "savings"} or any(
            value is not None for value in usage.values()):
        failures.append("invented_usage")
    return failures


def evaluate(corpus: dict) -> dict:
    validate_corpus(corpus)
    rows = []
    summary = {"total": len(corpus["cases"]), "passed": 0, "failed": 0, "groups": {}, "splits": {}}
    for case in corpus["cases"]:
        tools = corpus["tool_inventories"][case.get("tool_inventory", "default")]
        started = time.perf_counter()
        result = assess_task(case["task"], tools, case.get("context_budget", 2000))
        elapsed = (time.perf_counter() - started) * 1000
        failures = grade_assessment(case, result, tools)
        outcome = "failed" if failures else "passed"
        summary[outcome] += 1
        for dimension, label in (("groups", case["group"]), ("splits", case["split"])):
            counts = summary[dimension].setdefault(label, {"total": 0, "passed": 0, "failed": 0})
            counts["total"] += 1
            counts[outcome] += 1
        rows.append({"id": case["id"], "case": case, "offered_tools": tools,
                     "assessment": result, "passed": not failures, "failures": failures,
                     "elapsed_ms": round(elapsed, 6)})
    return {
        "schema": "parcimonia.assessment-evaluation/v1",
        "status": "failed" if summary["failed"] else "passed",
        "evidence_kind": "direct_deterministic_assessment",
        "provenance": {"corpus_sha256": _digest(_canonical(corpus)),
                       "corpus_hash_method": "sorted_compact_utf8_json",
                       "assessment_sha256": _digest(Path(__file__).with_name("assessment.py").read_bytes()),
                       "finder_sha256": _digest((Path(__file__).parents[1] / "skill_finder" / "finder.py").read_bytes()),
                       "evaluator_sha256": _digest(Path(__file__).read_bytes()),
                       "baseline_source_revision": corpus["baseline_source_revision"]},
        "summary": summary, "cases": rows,
        "model_selection": {"status": "not_run", "evaluated_cases": 0},
        "measured_usage": {"provider_tokens": None, "billed_cost": None, "savings": None},
        "limits": ["Candidate presence tests discovery, not ranking accuracy or verified capability.",
                   "Elapsed times cover local assessment calls only, not a Codex or model workflow.",
                   "Future codex criteria are retained but never graded by this offline runner.",
                   "Public synthetic regression cases do not establish generalization."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    force_utf8()
    try:
        report = evaluate(load_corpus(args.corpus))
        if args.output:
            write_json(args.output, report)
            print(json.dumps({"status": report["status"], "summary": report["summary"],
                              "model_selection": report["model_selection"]}, ensure_ascii=False))
        else:
            print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 1 if report["summary"]["failed"] else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
