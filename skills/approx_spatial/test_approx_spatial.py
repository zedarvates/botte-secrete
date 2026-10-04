import pytest

from skills.approx_spatial.benchmark import run
from skills.approx_spatial.oracle import Interval, SpatialEvidence, Verdict, evaluate_less_than


def evidence(admissible, *, guards=(), excluded=()):
    return SpatialEvidence(
        None if admissible is None else tuple(Interval(*bounds) for bounds in admissible),
        tuple(Interval(*bounds) for bounds in excluded),
        tuple(guards),
    )


def test_clear_yes_no_and_unknown_are_distinct():
    assert evaluate_less_than(evidence([(1.7, 2.2)]), 3.0) is Verdict.YES
    assert evaluate_less_than(evidence([(2.0, 2.4)]), 2.0) is Verdict.NO
    assert evaluate_less_than(evidence([(1.7, 2.2)]), 2.0) is Verdict.UNKNOWN


def test_unknown_is_not_coerced_to_no_when_hypotheses_span_threshold():
    value = evaluate_less_than(evidence([(1.0, 1.4), (3.2, 3.8)]), 2.0)
    assert value is Verdict.UNKNOWN
    assert value is not Verdict.NO


def test_guard_failure_and_missing_measurement_abstain():
    assert evaluate_less_than(evidence([(1.0, 1.2)], guards=("baseline_too_small",)), 2.0) is Verdict.UNKNOWN
    assert evaluate_less_than(evidence(None, guards=("missing_measurement",)), 2.0) is Verdict.UNKNOWN


def test_empty_admissible_set_is_conflict():
    assert evaluate_less_than(evidence([]), 2.0) is Verdict.CONFLICT


def test_no_midpoint_is_invented_and_exclusions_are_preserved():
    item = SpatialEvidence.from_mapping({
        "admissible_m": [[1.1, 1.9]],
        "excluded_m": [[0.2, 1.1], [1.9, 10.0]],
        "guard_failures": [],
    }).to_dict()
    assert "value_m" not in item
    assert item["admissible_m"] == [[1.1, 1.9]]
    assert item["excluded_m"] == [[0.2, 1.1], [1.9, 10.0]]


def test_invalid_interval_and_threshold_fail_closed():
    with pytest.raises(ValueError):
        Interval(2.0, 1.0)
    with pytest.raises(ValueError):
        evaluate_less_than(evidence([(1.0, 2.0)]), float("nan"))


def test_fixture_report_is_reproducible_and_all_cases_pass():
    first = run()
    second = run()
    assert first == second
    assert first["summary"]["failed"] == 0
    assert first["summary"]["total"] >= 9
    assert len(first["fixture_sha256"]) == 64
    assert len(first["results_sha256"]) == 64
