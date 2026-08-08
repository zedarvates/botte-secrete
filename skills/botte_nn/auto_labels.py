"""Deterministic, privacy-preserving labels for micro-NN grounding.

Only outcomes with an exact local oracle enter the verified ledger. Raw content
is never stored: a stable fingerprint deduplicates repeated samples across
process restarts, while the existing feature vector remains the training input.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Optional

_SEEN_BY_LOG: dict[str, set[str]] = {}
_LOCK = threading.Lock()


def compression_label(ratio: float) -> str:
    """Map measured output/input ratio to the model's three action classes."""
    value = max(0.0, min(float(ratio), 1.0))
    if value >= 0.90:
        return "none"
    if value >= 0.50:
        return "delta"
    return "heavy"


def _sample_fingerprint(model_name: str, features: list[float], actual_class: int,
                        oracle: str, sample_key: str) -> str:
    material = json.dumps({
        "model": model_name,
        "features": [round(float(value), 8) for value in features],
        "actual_class": int(actual_class),
        "oracle": oracle,
        "sample_key": sample_key,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _seen_fingerprints(log_file: Path) -> set[str]:
    key = str(log_file.resolve())
    cached = _SEEN_BY_LOG.get(key)
    if cached is not None:
        return cached
    seen: set[str] = set()
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                fingerprint = json.loads(line).get("sample_fingerprint", "")
            except (json.JSONDecodeError, AttributeError):
                continue
            if fingerprint:
                seen.add(str(fingerprint))
    _SEEN_BY_LOG[key] = seen
    return seen


def record_oracle_verdict(model_name: str, values: dict[str, float],
                          actual_label: str, *, oracle: str,
                          sample_key: str) -> Optional[str]:
    """Record one unique verified label from a deterministic local oracle."""
    from skills.botte_nn import calibration, features
    from skills.botte_nn.active_learning import DATA_DIR, record_feedback
    from skills.botte_nn.cli import _MODEL_META, _MODELS_DIR, _predict_python

    feature_vector = features.featurize(model_name, values)
    probabilities = _predict_python(
        str(_MODELS_DIR / f"{model_name}.json"), feature_vector
    )
    probabilities = calibration.apply_temperature(
        probabilities, calibration.load_temperature(model_name)
    )
    labels = _MODEL_META.get(model_name, {}).get("labels") or [
        f"class_{index}" for index in range(len(probabilities))
    ]
    if actual_label not in labels:
        raise ValueError(f"unknown label for {model_name}: {actual_label}")
    predicted_class = max(range(len(probabilities)), key=probabilities.__getitem__)
    actual_class = labels.index(actual_label)
    fingerprint = _sample_fingerprint(
        model_name, feature_vector, actual_class, oracle, sample_key
    )
    log_file = DATA_DIR / "inference_logs.jsonl"
    with _LOCK:
        seen = _seen_fingerprints(log_file)
        if fingerprint in seen:
            return None
        inference_id = record_feedback(
            model_name, feature_vector, predicted_class, actual_class,
            decision_source=f"automatic_oracle:{oracle}",
            confidence=float(max(probabilities)),
            outcome=f"oracle:{oracle}", sample_fingerprint=fingerprint,
        )
        seen.add(fingerprint)
    return inference_id


def record_compression_result(content: str, ratio: float, *,
                              roundtrip_ok: bool) -> Optional[str]:
    """Label a compression result only after an exact reversible roundtrip."""
    if not content or not roundtrip_ok:
        return None
    from skills.botte_nn.features import compressibility_values

    sample_key = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return record_oracle_verdict(
        "compressibility_predictor", compressibility_values(content),
        compression_label(ratio), oracle="compression_roundtrip",
        sample_key=sample_key,
    )


def record_cache_lookup(query: str, values: dict[str, float], *,
                        hit: bool, hit_kind: str) -> Optional[str]:
    """Label a response-cache lookup from its observed hit or miss result."""
    sample_key = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return record_oracle_verdict(
        "semantic_cache_hit_predictor", values, "hit" if hit else "miss",
        oracle=f"response_cache_{hit_kind}", sample_key=sample_key,
    )


__all__ = [
    "compression_label", "record_cache_lookup", "record_compression_result",
    "record_oracle_verdict",
]
