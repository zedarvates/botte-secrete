from skills.loop_optimizer.features import FEATURE_NAMES, extract_features
from skills.loop_optimizer.models import LoopRequest, LoopState, ProgressState


def test_features_have_stable_names_and_bounded_values():
    request = LoopRequest("loop", "goal", max_iterations=4, max_total_tokens=100, criticality=.8)
    state = LoopState("loop", iteration=2, context_tokens=80, progress=ProgressState.STALLED)
    features = extract_features(request, state, fingerprint_match=True,
                                failure_repeat=True, cache_history=3, verification_state=-1,
                                local_fail_rate=2)
    assert tuple(features) == FEATURE_NAMES
    assert all(0.0 <= value <= 1.0 for value in features.values())
    assert features["iteration_ratio"] == .5
    assert features["budget_ratio"] == .8


def test_solved_state_scores_above_regressed_state():
    request = LoopRequest("loop", "goal")
    solved = extract_features(request, LoopState("loop", progress=ProgressState.SOLVED))
    regressed = extract_features(request, LoopState("loop", progress=ProgressState.REGRESSED))
    assert solved["progress_score"] > regressed["progress_score"]
