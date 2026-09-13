"""Recheck published study evidence without importing or running either model.

This checks integrity and reproducible scoring, not independent attestation of
the historical inference or qualification on user tasks.
"""
from skills.tool_router.needle2_study import (
    BOUNDARY, ROOT, checked_report, compare, digest, load_protocol, read_json, select,
)


def test_published_calibration_evidence_reproduces_the_stop_decision():
    evidence = ROOT / "docs/validation"
    manifest = read_json(evidence / "needle2-study-validation-v1.json")
    for name, expected in manifest["evidence_sha256"].items():
        assert digest((ROOT / name).read_bytes()) == expected, name

    protocol, protocol_hash, splits = load_protocol()
    needle_path = evidence / "needle2-study-calibration-native-v1.json"
    needle = checked_report(needle_path, protocol, protocol_hash, splits)
    generalist = checked_report(
        evidence / "needle2-study-calibration-generalist-v1.json",
        protocol, protocol_hash, splits,
    )
    assert compare(needle, generalist) == read_json(
        evidence / "needle2-study-comparison-v1.json"
    )
    selection = {
        **select(needle, protocol["thresholds"]),
        "protocol_sha256": protocol_hash,
        "calibration_sha256": digest(needle_path.read_bytes()),
    }
    assert selection == read_json(evidence / "needle2-study-selection-v1.json")
    assert selection["decision"] == manifest["selection_decision"] == "stop_insufficient_safe_coverage"
    assert selection["selected_threshold"] is None
    assert len(needle["cases"]) == manifest["native_needle_case_attempts"] == 20
    assert len(generalist["cases"]) == manifest["real_generalist_case_attempts"] == 20
    assert manifest["validation_case_attempts"] == 0
    assert sum(bool(row.get("runtime_error")) for report in (needle, generalist)
               for row in report["cases"]) == manifest["runtime_errors"] == 0
    for key, expected in BOUNDARY.items():
        assert manifest[key] == expected, key
