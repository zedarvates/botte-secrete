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
# Overridable per project via .botte/policy.md: _BELT_CONFIDENCE = 0.80
CONFIDENCE = 0.66


def _load_confidence() -> float:
    """Load belt confidence threshold from project policy if configured."""
    try:
        from skills.preflight.policy import load
        policy = load(".")
        import re
        m = re.search(r"_BELT_CONFIDENCE\s*=\s*([0-9.]+)", policy)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return CONFIDENCE


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


def binary_router_prediction(complexity: float, budget_ratio: float,
                             has_local: bool) -> Optional[dict]:
    """Return the raw calibrated binary_router prediction, without abstention.

    The result is safe for shadow telemetry: routing can keep using its current
    policy while every comparable decision receives the model prediction that a
    later explicit verdict can verify. Missing model / any error -> None.
    """
    features = featurize_binary_router(complexity, budget_ratio, has_local)
    try:
        from skills.botte_nn.cli import _predict_python, _MODELS_DIR
        from skills.botte_nn import calibration

        model_path = _MODELS_DIR / "binary_router.json"
        if not model_path.exists():
            return None
        out = _predict_python(str(model_path), features)  # [P(local), P(cloud)]
        if not out or len(out) < 2:
            return None
        out = calibration.apply_temperature(
            out, calibration.load_temperature("binary_router")
        )
        predicted_class = 0 if out[0] >= out[1] else 1
        return {
            "features": features,
            "predicted_class": predicted_class,
            "label": "local" if predicted_class == 0 else "cloud",
            "confidence": float(max(out)),
        }
    except Exception:  # noqa: BLE001 — the belt must never break routing
        return None


def confident_hint(prediction: Optional[dict]) -> Optional[tuple[str, float]]:
    """Apply the configured abstention threshold to one raw prediction."""
    if prediction is None or prediction["confidence"] < _load_confidence():
        return None
    return prediction["label"], prediction["confidence"]


def local_vs_cloud_hint(complexity: float, budget_ratio: float,
                        has_local: bool) -> Optional[tuple[str, float]]:
    """('local'|'cloud', confidence) from binary_router, or None if abstaining."""
    return confident_hint(
        binary_router_prediction(complexity, budget_ratio, has_local)
    )
