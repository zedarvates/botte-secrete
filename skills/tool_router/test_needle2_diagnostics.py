"""Offline error attribution, immutable archive checks and output handling."""
import copy
import json
from pathlib import Path

import pytest

from . import needle2_diagnostics as diagnostics
from . import needle2_study as study


@pytest.mark.parametrize("expected,actual,expected_args,actual_args,outcome", [
    ("memory_wiki", "memory_wiki", {}, {}, "positive_exact"),
    ("memory_wiki", "memory_history", {}, {"key": "example"}, "positive_wrong_tool"),
    ("memory_wiki", "memory_wiki", {}, {"query": ""}, "positive_wrong_arguments"),
    ("memory_scribe", "memory_scribe", {"text": "État"}, {"text": "état"}, "positive_wrong_arguments"),
    ("memory_wiki", None, {}, {}, "positive_abstention"),
    (None, "memory_wiki", {}, {}, "negative_proposal"),
    (None, None, {}, {}, "negative_abstention"),
])
def test_outcomes_keep_exact_arguments_and_negative_proposals_separate(
        expected, actual, expected_args, actual_args, outcome):
    case = {"id": "example", "expected_tool": expected, "expected_arguments": expected_args}
    row = {"route": {"tool_name": actual, "arguments": actual_args, "reason": "recorded"}}
    before = copy.deepcopy((case, row))
    result = diagnostics._classify(case, row)
    assert result["outcome"] == outcome
    assert (case, row) == before


def test_argument_diff_distinguishes_missing_unexpected_and_changed():
    case = {"id": "example", "expected_tool": "example",
            "expected_arguments": {"missing": "x", "changed": "État", "same": 2}}
    row = {"route": {"tool_name": "example", "reason": "recorded",
                     "arguments": {"unexpected": "", "changed": "état", "same": 2}}}
    result = diagnostics._classify(case, row)["argument_difference"]
    assert result["missing"] == ["missing"]
    assert result["unexpected"] == ["unexpected"]
    assert result["changed"] == ["changed"]


def test_published_archive_is_reproduced_without_model_or_tool_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline diagnostics attempted runtime work")

    monkeypatch.setattr(study.Generalist, "__init__", forbidden)
    monkeypatch.setattr(study.Needle2ToolRouter, "__init__", forbidden)
    monkeypatch.setattr(study, "collect", forbidden)
    report = diagnostics.diagnose_archive()
    expected = diagnostics.read_json(study.ROOT / "docs/validation/needle2-error-diagnostics-v1.json")
    assert report == expected
    assert report["models"]["needle"]["counts"] == {
        "positive_exact": 4, "positive_wrong_tool": 1, "positive_wrong_arguments": 2,
        "positive_abstention": 3, "negative_proposal": 4, "negative_abstention": 6,
    }
    assert report["models"]["generalist"]["counts"] == {
        "positive_exact": 4, "positive_wrong_tool": 1, "positive_wrong_arguments": 5,
        "positive_abstention": 0, "negative_proposal": 6, "negative_abstention": 4,
    }
    for model in report["models"].values():
        assert sum(model["counts"].values()) == 20
        assert all(row["id"].startswith("cal-") for row in model["cases"])
    assert report["models"]["needle"]["abstentions_by_recorded_reason"]["negative"] == {
        "invalid_arguments": 1, "model_abstained": 3, "ungrounded_arguments": 2,
    }
    assert report["models"]["generalist"]["abstentions_by_recorded_reason"]["negative"] == {
        "invalid_model_output": 3, "model_abstained": 1,
    }
    assert report["new_inference_attempts"] == report["validation_case_attempts"] == 0
    assert report["selected_threshold"] is None
    assert report["speedup_claim_allowed"] is False
    assert all(report[key] == value for key, value in study.BOUNDARY.items())


@pytest.mark.parametrize("path", [
    diagnostics.MANIFEST,
    diagnostics.PREFIX + "calibration-native-v1.json",
    diagnostics.PREFIX + "calibration-generalist-v1.json",
    diagnostics.PREFIX + "selection-v1.json",
    diagnostics.PREFIX + "comparison-v1.json",
    "skills/tool_router/needle2_calibration_fr_v1.jsonl",
])
def test_changed_inputs_fail_before_diagnostic_classification(monkeypatch, path):
    original = Path.read_bytes

    def changed(self):
        raw = original(self)
        return raw + b"\n" if self == study.ROOT / path else raw

    def forbidden(*args, **kwargs):
        pytest.fail("changed evidence reached classification")

    monkeypatch.setattr(Path, "read_bytes", changed)
    monkeypatch.setattr(diagnostics, "_diagnose", forbidden)
    with pytest.raises(ValueError, match="changed"):
        diagnostics.diagnose_archive()


def test_cli_writes_reproducible_output_and_refuses_overwrite(tmp_path, capsys, monkeypatch):
    output = tmp_path / "diagnostic.json"
    assert diagnostics.main(["--output", str(output)]) == 0
    saved = output.read_bytes()
    result = json.loads(saved)
    printed = json.loads(capsys.readouterr().out)
    assert printed["counts"]["needle"] == result["models"]["needle"]["counts"]

    def forbidden():
        pytest.fail("output collision reached archive processing")

    monkeypatch.setattr(diagnostics, "diagnose_archive", forbidden)
    assert diagnostics.main(["--output", str(output)]) == 2
    assert output.read_bytes() == saved
    assert json.loads(capsys.readouterr().out)["detail"] == "output exists"


def test_cli_does_not_write_a_result_for_invalid_evidence(tmp_path, capsys, monkeypatch):
    def invalid():
        raise ValueError("frozen evidence changed")

    monkeypatch.setattr(diagnostics, "diagnose_archive", invalid)
    output = tmp_path / "diagnostic.json"
    assert diagnostics.main(["--output", str(output)]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["activation_allowed"] is False
