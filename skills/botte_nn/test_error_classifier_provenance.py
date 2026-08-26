#!/usr/bin/env python3
"""Reproducibility and provenance guards for error_classifier."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .training.distill_error_classifier import (
    _core_payload,
    _stable_sha256,
    build_dataset,
    build_provenance,
)
from .training.train import TinyNN

MODEL_PATH = Path(__file__).parent / "models" / "error_classifier.json"
EXPECTED_CORE_SHA256 = "212f2b36e1684c1bd4013943b5a47af2666b6dca4832cf18d64565f1d12c1e15"


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== error_classifier provenance tests ==")
    stored = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    core = _core_payload(stored)
    provenance = stored.get("provenance", {})

    _ok("inference tensors are unchanged",
        _stable_sha256(core) == EXPECTED_CORE_SHA256, state)
    _ok("stored core fingerprint matches tensors",
        provenance.get("weights", {}).get("core_sha256") == EXPECTED_CORE_SHA256, state)
    _ok("model remains G1 and does not claim production observations",
        provenance.get("maturity") == "G1"
        and provenance.get("label_contract", {}).get("production_observations") is False,
        state)

    X, y = build_dataset()
    idx = np.random.default_rng(42).permutation(len(y))
    test_count = max(6, len(y) // 5)
    test_idx, train_idx = idx[:test_count], idx[test_count:]
    X_train, y_train = X[train_idx], y[train_idx]
    expected = np.zeros((len(y_train), 6))
    expected[np.arange(len(y_train)), y_train] = 1.0
    np.random.seed(0)
    reproduced = TinyNN([12, 16, 6], ["relu", "softmax"])
    reproduced.train(X_train, expected, epochs=1500, lr=0.05, verbose=False)
    reproduced_data = reproduced.export_json()

    tensor_pairs = zip(
        core["weights"] + core["biases"],
        reproduced_data["weights"] + reproduced_data["biases"],
    )
    _ok("training reproduces every tensor within 1e-12",
        all(np.allclose(a, b, rtol=0, atol=1e-12) for a, b in tensor_pairs), state)

    held_out_accuracy = float(np.mean(
        reproduced.predict(X[test_idx]).argmax(axis=1) == y[test_idx]
    ))
    rebuilt = build_provenance(core, X, y, train_idx, test_idx, held_out_accuracy)
    _ok("corpus and expanded dataset fingerprints reproduce",
        rebuilt["corpus"]["sha256"] == provenance.get("corpus", {}).get("sha256")
        and rebuilt["dataset"]["sha256"] == provenance.get("dataset", {}).get("sha256"),
        state)
    _ok("held-out result reproduces as 32/34 (94.12%)",
        rebuilt["evaluation"] == provenance.get("evaluation")
        and rebuilt["evaluation"]["correct"] == 32
        and rebuilt["evaluation"]["total"] == 34,
        state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
