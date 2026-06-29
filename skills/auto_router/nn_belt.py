"""NN belt — the trained binary_router micro-NN advises local vs cloud, with
abstention, at 0 cloud tokens.

The router's effort heuristic (effort.py) picks a tier from keyword signals. This
belt adds a second, *learned* opinion on the local-vs-cloud question using the
exact signals binary_router was trained on (train_model.generate_binary_router):

    [0] task_complexity    in [0,1]   <- effort score
    [1] token_budget_ratio in [0,1]   <- daily budget remaining
    [2] has_local_model    in {0,1}

It returns a hint only when confident; otherwise it abstains and the heuristic
stands. It never invents a cloud model, and (v1) the router only ever uses it to
nudge a *borderline* task toward local — so the belt can save tokens but never
silently raise cost or quality risk. Absent model / any error -> silent abstain.

This is the "smart belt above the harness": a cheap local classifier that filters
the easy local/cloud calls so they never need the expensive reasoning model. As
the active-learning loop (skills.botte_nn.active_learning) collects real routing
outcomes, binary_router sharpens and the belt can be trusted further.
"""

from __future__ import annotations

from typing import Optional

# Below this max-softmax confidence the belt abstains -> the heuristic decides.
CONFIDENCE = 0.66


def featurize_binary_router(complexity: float, budget_ratio: float,
                            has_local: bool) -> list[float]:
    """Map router signals to the 3-feature vector binary_router expects.

    Delegates to skills.botte_nn.features (the single, validated source of truth
    for every model's feature schema)."""
    from skills.botte_nn import features

    return features.featurize(
        "binary_router",
        features.binary_router_values(complexity, budget_ratio, has_local),
    )


def local_vs_cloud_hint(complexity: float, budget_ratio: float,
                        has_local: bool) -> Optional[tuple[str, float]]:
    """('local'|'cloud', confidence) from binary_router, or None if abstaining.

    None means: model file unavailable, any error, or confidence below threshold.
    Pure function with no side effects — safe to call from a routing decision.
    """
    features = featurize_binary_router(complexity, budget_ratio, has_local)
    try:
        from skills.botte_nn.cli import _predict_python, _MODELS_DIR

        model_path = _MODELS_DIR / "binary_router.json"
        if not model_path.exists():
            return None
        out = _predict_python(str(model_path), features)  # [P(local), P(cloud)]
    except Exception:  # noqa: BLE001 — the belt must never break routing
        return None

    if not out or len(out) < 2:
        return None
    # Calibrate the raw softmax so the CONFIDENCE cutoff is meaningful (Hermes #3).
    # Identity (T=1.0) until binary_router is actually calibrated, so behaviour is
    # unchanged by default.
    from skills.botte_nn import calibration

    out = calibration.apply_temperature(out, calibration.load_temperature("binary_router"))
    label = "local" if out[0] >= out[1] else "cloud"
    confidence = float(max(out))
    if confidence < CONFIDENCE:
        return None
    return label, confidence
