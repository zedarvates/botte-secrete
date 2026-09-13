"""Opt-in Needle 2 proposal and evaluation CLI; never executes model tools."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

from skills.console_utf8 import force_utf8
from skills.memory_hub.shared_contract import decode, encode
from .base import LexicalToolRouter
from .memory_pilot import CONTRACT_VERSION, catalog_sha256, memory_tools, propose
from .needle2_adapter import Needle2ToolRouter
from .needle2_worker import PACKAGE_VERSION


def source_hashes():
    root = Path(__file__).resolve().parents[2]
    names = ["skills/cli.py", "skills/memory_hub/shared_contract.py"]
    names += ["skills/tool_router/" + name + ".py" for name in
              ("base", "memory_pilot", "needle2_adapter", "needle2_cli", "needle2_worker")]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def evaluate(router, dataset):
    """Strict call+arguments equality; abstention scored only on negative cases.

    This synthetic suite is implementation evidence, never a training ledger or
    a production activation gate. Baseline and candidate get identical inputs.
    """
    data = Path(dataset).read_bytes()
    cases = [decode(line) for line in data.splitlines() if line.strip()]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("dataset must have unique, nonempty cases")
    results, timings = [], []
    for case in cases:
        started = time.perf_counter()
        route = router.route(case["query"], memory_tools())
        elapsed = (time.perf_counter() - started) * 1000
        timings.append(elapsed)
        positive = case["expected_tool"] is not None
        results.append({"id": case["id"], "kind": case["kind"],
                        "positive": positive,
                        "tool_correct": route.tool_name == case["expected_tool"],
                        "call_correct": route.tool_name == case["expected_tool"]
                            and dict(route.arguments) == case["expected_arguments"],
                        "abstained": route.abstained,
                        "latency_ms": round(elapsed, 3), "route": asdict(route)})
    positives = [r for r in results if r["positive"]]
    negatives = [r for r in results if not r["positive"]]
    ordered = sorted(timings)
    def ratio(rows, key):
        return sum(r[key] for r in rows) / len(rows) if rows else None
    return {"dataset_sha256": hashlib.sha256(data).hexdigest(),
            "total": len(results), "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "tool_accuracy": ratio(results, "tool_correct"),
            "positive_exact_call_accuracy": ratio(positives, "call_correct"),
            "negative_abstention_accuracy": ratio(negatives, "abstained"),
            "false_proposals_on_negative_cases": sum(not r["abstained"] for r in negatives),
            "p95_latency_ms": round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 3),
            "first_query_ms": round(timings[0], 3),
            "runtime_error_count": sum(r["route"]["reason"] in {
                "needle2_library_missing", "needle2_runtime_error", "needle2_timeout"} for r in results),
            "cases": results}


def main(argv=None):
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tools", help="show the five read-only schemas")
    route = sub.add_parser("route", help="return an advisory memory call")
    route.add_argument("query")
    route.add_argument("--project-id", required=True)
    bench = sub.add_parser("benchmark", help="compare lexical and Needle on synthetic French cases")
    bench.add_argument("--dataset", type=Path,
                       default=Path(__file__).with_name("needle2_cases_fr.jsonl"))
    bench.add_argument("--output", type=Path)
    for command in (route, bench):
        command.add_argument("--library", type=Path, help="existing local Needle 2 native library")
        command.add_argument("--engine-python", help="interpreter with cactus-needle==" + PACKAGE_VERSION)
        command.add_argument("--confidence-threshold", type=float, default=0.9)
        command.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    try:
        if args.command == "tools":
            result = {"schema_version": CONTRACT_VERSION, "catalog_sha256": catalog_sha256(),
                      "tools": [t.as_dict() for t in memory_tools()]}
        else:
            with Needle2ToolRouter(args.library, python_executable=args.engine_python,
                                  confidence_threshold=args.confidence_threshold,
                                  timeout=args.timeout) as router:
                if args.command == "route":
                    result = propose(args.query, router, args.project_id)
                else:
                    result = {"schema_version": CONTRACT_VERSION, "mode": "advisory_evaluation",
                              "recorded_at": datetime.now(timezone.utc).isoformat(),
                              "source_files_sha256": source_hashes(),
                              "corpus": "synthetic_exploratory_not_production_evidence",
                              "catalog_sha256": catalog_sha256(),
                              "baseline": evaluate(LexicalToolRouter(), args.dataset),
                              "candidate": evaluate(router, args.dataset),
                              "runtime": {"package_version": PACKAGE_VERSION,
                                          "platform": platform.system(), "architecture": platform.machine(),
                                          "host_python": platform.python_version(),
                                          "worker": router.worker_runtime,
                                          "library_sha256": router.library_sha256,
                                          "startup_ms": router.startup_ms},
                              "confidence_threshold": args.confidence_threshold,
                              "local_generalist_comparison": "not_measured",
                              "native_peak_memory": "not_measured",
                              "executed": False, "activation_allowed": False}
                    if args.output:
                        # Explicit output only; never overwrite an earlier evidence record.
                        with args.output.open("x", encoding="utf-8") as handle:
                            json.dump(result, handle, ensure_ascii=False, allow_nan=False, indent=2)
                            handle.write("\n")
        displayed = result
        if args.command == "benchmark" and args.output:
            displayed = {**result, "baseline": {k: v for k, v in result["baseline"].items() if k != "cases"},
                         "candidate": {k: v for k, v in result["candidate"].items() if k != "cases"}}
        print(encode(displayed).decode("utf-8"))
        if args.command == "benchmark" and result["candidate"]["runtime_error_count"]:
            return 3
        if args.command == "route" and result["route"]["tool_name"] is None:
            return 3
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(encode({"error": type(error).__name__, "executed": False}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
