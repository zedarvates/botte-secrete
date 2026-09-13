"""Explain the frozen v1 calibration errors offline, without changing scoring."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from skills.memory_hub.shared_contract import decode, encode
from .needle2_study import (
    BOUNDARY, ROOT, checked_report, compare, digest, load_protocol, read_json,
    select, write_json,
)

MANIFEST = "docs/validation/needle2-study-validation-v1.json"
MANIFEST_SHA256 = "f912faf2591007b0ad8b1963e845d2ff0294024947c16a1756181cfbdb191f56"
PREFIX = "docs/validation/needle2-study-"
OUTCOMES = (
    "positive_exact", "positive_wrong_tool", "positive_wrong_arguments",
    "positive_abstention", "negative_proposal", "negative_abstention",
)


def _classify(case, row):
    """Classify an already checked row against its frozen, unmodified label."""
    route = row["route"]
    expected, actual = case["expected_tool"], route["tool_name"]
    arguments = case["expected_arguments"]
    if expected is None:
        outcome = "negative_abstention" if actual is None else "negative_proposal"
    elif actual is None:
        outcome = "positive_abstention"
    elif actual != expected:
        outcome = "positive_wrong_tool"
    elif route["arguments"] != arguments:
        outcome = "positive_wrong_arguments"
    else:
        outcome = "positive_exact"
    result = {"id": case["id"], "expected_tool": expected,
              "proposed_tool": actual, "outcome": outcome,
              "recorded_reason": route["reason"]}
    if outcome == "positive_wrong_arguments":
        proposed = route["arguments"]
        result["argument_difference"] = {
            "missing": sorted(arguments.keys() - proposed.keys()),
            "unexpected": sorted(proposed.keys() - arguments.keys()),
            "changed": sorted(k for k in arguments.keys() & proposed.keys()
                              if arguments[k] != proposed[k]),
            "expected": arguments, "proposed": proposed,
        }
    return result


def _diagnose(report, cases):
    rows = [_classify(case, row) for case, row in zip(cases, report["cases"])]
    counts = Counter(row["outcome"] for row in rows)
    groups = sorted({row["expected_tool"] or "no_tool_expected" for row in rows})
    return {
        "counts": {key: counts[key] for key in OUTCOMES},
        "by_expected_tool": {
            key: dict(sorted(Counter(row["outcome"] for row in rows
                                    if (row["expected_tool"] or "no_tool_expected") == key).items()))
            for key in groups
        },
        "abstentions_by_recorded_reason": {
            kind: dict(sorted(Counter(row["recorded_reason"] for row in rows
                                      if row["outcome"] == kind + "_abstention").items()))
            for kind in ("positive", "negative")
        },
        "cases": rows,
    }


def diagnose_archive():
    """Accept only the published v1 archive, including its stop decision."""
    raw = (ROOT / MANIFEST).read_bytes()
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError("frozen study manifest changed")
    manifest = decode(raw)
    for name, expected in manifest["evidence_sha256"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("frozen evidence changed: " + name)
    protocol, protocol_hash, splits = load_protocol()
    needle = checked_report(ROOT / (PREFIX + "calibration-native-v1.json"),
                            protocol, protocol_hash, splits)
    generalist = checked_report(ROOT / (PREFIX + "calibration-generalist-v1.json"),
                                protocol, protocol_hash, splits)
    comparison = compare(needle, generalist)
    if comparison != read_json(ROOT / (PREFIX + "comparison-v1.json")):
        raise ValueError("archived comparison does not reproduce")
    selection = {
        **select(needle, protocol["thresholds"]), "protocol_sha256": protocol_hash,
        "calibration_sha256": manifest["evidence_sha256"][PREFIX + "calibration-native-v1.json"],
    }
    if (selection != read_json(ROOT / (PREFIX + "selection-v1.json"))
            or selection["decision"] != "stop_insufficient_safe_coverage"
            or selection["selected_threshold"] is not None
            or needle["split"] != "calibration"):
        raise ValueError("frozen calibration stop decision differs")
    return {
        "schema_version": "botte.needle2-error-diagnostics/v1",
        "operation": "offline_classification_of_archived_calibration",
        "source_sha256": {MANIFEST: MANIFEST_SHA256, **manifest["evidence_sha256"]},
        "diagnostic_source_sha256": digest(Path(__file__).read_bytes()),
        "protocol_sha256": protocol_hash,
        "split": "calibration",
        "selection_decision": selection["decision"],
        "selected_threshold": None,
        "threshold_filter_applied": False,
        "new_inference_attempts": 0,
        "validation_case_attempts": 0,
        "models": {"needle": _diagnose(needle, splits["calibration"]),
                   "generalist": _diagnose(generalist, splits["calibration"])},
        "speedup_claim_allowed": False,
        "limitations": comparison["limitations"] + [
            "post_hoc_error_description_not_a_new_quality_measurement",
            "recorded_abstention_reason_is_not_independent_model_intent_evidence",
            "no_prediction_of_benefit_from_catalog_or_argument_changes",
        ],
        **BOUNDARY,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output exists")
        report = diagnose_archive()
        write_json(args.output, report)
        summary = {k: v for k, v in report.items()
                   if k not in {"source_sha256", "models", "limitations"}}
        summary["counts"] = {key: value["counts"] for key, value in report["models"].items()}
        print(encode(summary).decode("utf-8"))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(encode({"error": type(error).__name__, "detail": str(error)[:160],
                      **BOUNDARY}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
