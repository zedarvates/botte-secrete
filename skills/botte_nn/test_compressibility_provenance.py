#!/usr/bin/env python3
"""Reproducibility and provenance guards for compressibility_predictor."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .cli import _predict_python
from .training.distill_compressibility_predictor import (
    _core_payload,
    _stable_sha256,
    build_dataset,
    build_provenance,
    export_model,
    predict,
    stratified_split,
    train_model,
)

MODEL_PATH = Path(__file__).parent / "models" / "compressibility_predictor.json"
EXPECTED_CORE_SHA256 = "374b449fade9f84c79ea8bf66dec2d091c55644d776d4c611d546b032b26a916"


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== compressibility_predictor provenance tests ==")
    stored = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    core = _core_payload(stored)
    provenance = stored.get("provenance", {})
    _ok("inference tensors match the reviewed fingerprint",
        _stable_sha256(core) == EXPECTED_CORE_SHA256, state)
    _ok("stored core fingerprint matches tensors",
        provenance.get("weights", {}).get("core_sha256") == EXPECTED_CORE_SHA256, state)
    _ok("model remains G1 and does not claim production observations",
        provenance.get("maturity") == "G1"
        and provenance.get("label_contract", {}).get("production_observations") is False,
        state)

    X, y, evidence = build_dataset()
    train_idx, test_idx = stratified_split(y)
    tensors = train_model(X[train_idx], y[train_idx])
    reproduced = export_model(tensors)
    tensor_pairs = zip(
        core["weights"] + core["biases"],
        reproduced["weights"] + reproduced["biases"],
    )
    _ok("training reproduces every tensor within 1e-12",
        all(np.allclose(a, b, rtol=0, atol=1e-12) for a, b in tensor_pairs), state)
    accuracy = float(np.mean(predict(X[test_idx], tensors) == y[test_idx]))
    rebuilt = build_provenance(
        reproduced, X, y, evidence, train_idx, test_idx, accuracy,
    )
    _ok("compression evidence and dataset fingerprints reproduce",
        rebuilt["corpus"]["sha256"] == provenance.get("corpus", {}).get("sha256")
        and rebuilt["dataset"]["sha256"] == provenance.get("dataset", {}).get("sha256"),
        state)
    _ok("every corpus case passed exact reversible roundtrip",
        all(row["roundtrip"] is True for row in evidence), state)
    _ok("held-out accuracy and class balance reproduce",
        rebuilt["evaluation"] == provenance.get("evaluation")
        and all(rebuilt["dataset"]["class_counts"]), state)
    runtime_predictions = np.array([
        int(np.argmax(_predict_python(str(MODEL_PATH), row.tolist())))
        for row in X[test_idx]
    ])
    _ok("public inference format reproduces the held-out result",
        float(np.mean(runtime_predictions == y[test_idx])) == accuracy, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
