"""Check archive data integrity separately from integrated-source qualification.

This checks integrity and reproducible scoring, not independent attestation of
the historical inference or qualification on user tasks.
"""
from skills.tool_router.needle2_study import (
    BOUNDARY, ROOT, checked_report, compare, digest, load_protocol, read_json, select,
)
import pytest

from . import needle2_study as study
from .needle2_test_fixtures import historical_bindings, IMMUTABLE_JSON


def test_immutable_calibration_data_and_scores_remain_consistent():
    """Recompute archived rows, without accepting their old source bindings.

    Source-exact historical reproduction runs separately at the pinned commit.
    This checks the current score checker against immutable observations only;
    it neither qualifies current model inference nor executes a validation split.
    """
    evidence = ROOT / "docs/validation"
    manifest, protocol, source_drift, attachment_drift = historical_bindings()
    for filename in IMMUTABLE_JSON:
        name = "docs/validation/" + filename
        expected = manifest["evidence_sha256"][name]
        assert digest((ROOT / name).read_bytes()) == expected, name
    assert source_drift, "integrated sources must not pass as the historical source"
    assert "skills/tool_router/test_needle2_study.py" in attachment_drift
    assert protocol["catalog_sha256"] == study.catalog_sha256()
    splits = {}
    for split, info in protocol["splits"].items():
        raw = (ROOT / info["path"]).read_bytes()
        assert digest(raw) == info["sha256"], split
        splits[split] = [study.decode(line) for line in raw.splitlines() if line.strip()]
    protocol_hash = digest(study.PROTOCOL.read_bytes())
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


def test_historical_source_bindings_refuse_integrated_run_before_runtime(tmp_path, monkeypatch, capsys):
    _, _, drift, _ = historical_bindings()
    assert {"skills/cli.py", "skills/memory_hub/shared_contract.py", "skills/tool_router/memory_pilot.py"} <= set(drift)

    def forbidden(*args, **kwargs):
        pytest.fail("historical protocol drift reached a model runtime")

    monkeypatch.setattr(study, "Generalist", forbidden)
    monkeypatch.setattr(study, "Needle2ToolRouter", forbidden)
    with pytest.raises(ValueError, match="study source changed"):
        load_protocol()
    output = tmp_path / "must-not-exist.json"
    assert study.main(["run", "--backend", "needle", "--split", "calibration",
                       "--output", str(output)]) == 2
    printed = study.decode(capsys.readouterr().out.encode("utf-8"))
    assert printed["detail"].startswith("study source changed:")
    assert not output.exists() and not output.with_suffix(".json.jsonl").exists()
    assert printed["activation_allowed"] is False and printed["executed"] is False
