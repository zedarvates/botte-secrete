import pytest

from skills.loop_optimizer.features import FEATURE_NAMES
from skills.loop_optimizer.models import LoopAction
from skills.loop_optimizer.policy import (
    Trajectory, deterministic_fallback, policy_activation_allowed, save_verified, split_temporal,
)


def _trajectory(index=0):
    return Trajectory({name: index / 10 for name in FEATURE_NAMES}, LoopAction.RETRY_LOCAL, True, True)


def test_temporal_split_keeps_newest_items_out_of_training():
    train, holdout = split_temporal([_trajectory(i) for i in range(10)])
    assert len(train) == 8 and len(holdout) == 2
    assert train[-1].features["iteration_ratio"] < holdout[0].features["iteration_ratio"]


def test_unverified_trajectory_and_wrong_features_are_rejected():
    with pytest.raises(ValueError):
        Trajectory({}, LoopAction.STOP, False, False)
    with pytest.raises(ValueError):
        Trajectory({name: 0.0 for name in FEATURE_NAMES[:-1]}, LoopAction.STOP, True, True)


def test_policy_gate_requires_volume_success_and_ten_percent_saving():
    assert not policy_activation_allowed(1999, baseline_success=1, policy_success=1, baseline_tokens=100, policy_tokens=80)
    assert policy_activation_allowed(2000, baseline_success=.9, policy_success=.9, baseline_tokens=100, policy_tokens=90)
    assert not policy_activation_allowed(2000, baseline_success=.9, policy_success=.89, baseline_tokens=100, policy_tokens=80)


def test_verified_dataset_persists_and_fallback_is_local():
    import json
    path = __import__("pathlib").Path(".") / "_policy-test.json"
    try:
        assert save_verified(path, [_trajectory()]) == 1
        assert json.loads(path.read_text(encoding="utf-8"))["count"] == 1
    finally:
        path.unlink(missing_ok=True)
    assert deterministic_fallback({}) is LoopAction.RETRY_LOCAL
