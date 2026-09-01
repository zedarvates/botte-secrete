#!/usr/bin/env python3
"""Distill compressibility_predictor from deterministic compression outcomes.

Every label comes from the universal compressor's measured output/input ratio,
and is accepted only after the reversible store restores the original content
exactly.  The embedded corpus covers text, JSON, code, logs, and tool output.
It provides reproducible G1 evidence; G2 still requires 1,000 deduplicated
production observations and a temporal holdout.

    python -m skills.botte_nn.training.distill_compressibility_predictor
    python -m skills.botte_nn.training.distill_compressibility_predictor --save
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from skills.botte_nn import features
from skills.botte_nn.auto_labels import compression_label
from skills.botte_nn.cli import _MODELS_DIR, _predict_python
from skills.universal_compressor.compressor import compress, flush_store, restore

_LABELS = ["none", "delta", "heavy"]
_SOURCE_COMMIT = "8a22992bdec939446ee261ad883fd4a9eccc23ef"
_TRAINER = "skills/botte_nn/training/distill_compressibility_predictor.py"
_FEATURE_DECIMALS = 12
_TRAINING_DECIMALS = 12


def _stable_sha256(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _core_payload(model_data: dict) -> dict:
    """Return inference tensors only, excluding auditable metadata."""
    return {
        key: model_data[key]
        for key in ("layers", "weights", "biases", "activations")
    }


def build_corpus() -> list[tuple[str, str]]:
    """Return diverse, deterministic content without production/private data."""
    cases: list[tuple[str, str]] = []
    for index in range(40):
        cases.extend([
            ("text", f"Unique status {index}: worker ready; queue depth {index % 7}."),
            ("text", chr(97 + index % 20) * (20 + index % 12)),
            ("text", "\n".join(
                f"Step {line}: inspect component {index}-{line} and retain evidence."
                for line in range(8)
            )),
            ("text", (f"ERROR component-{index} retry pending\n" * (15 + index % 8))),
            ("json", json.dumps({
                "request": index,
                "status": "ready",
                "items": [{"id": item, "ok": item % 2 == 0} for item in range(8)],
            }, indent=2)),
            ("json", json.dumps({"id": index, "ok": True}, separators=(",", ":"))),
            ("json", json.dumps({
                "values": list(range(2 + index % 3)), "status": "ready",
            }, indent=2)),
            ("code", "\n".join([
                "# deterministic example used for compression measurement",
                "import json",
                "import pathlib",
                f"VALUE = {index}",
                "def encode(value):",
                "    # serialize one public test value",
                "    return json.dumps({'value': value})",
            ])),
            ("code", "\n".join([
                "# measured comment",
                "# removable detail",
                "import json",
                f"VALUE = {index}",
                "def encode():",
                "    return json.dumps(VALUE)",
            ])),
            ("log", "\n".join(
                f"2026-08-26T12:{minute:02d}:00 ERROR worker={index} retry={minute} failed"
                for minute in range(25)
            )),
            ("tool_output", "\n".join(
                f"case_{line:04d}: {'PASSED' if line % 3 else 'FAILED'} worker={index}"
                for line in range(140)
            )),
        ])
    return cases


def build_dataset():
    """Measure compression and require an exact reversible roundtrip per case."""
    X, y, evidence = [], [], []
    flush_store()
    try:
        for content_type, content in build_corpus():
            result = compress(
                content, content_type=content_type, reversible=True, learn=False,
            )
            if not result.reversible_key or restore(result.reversible_key) != content:
                raise RuntimeError("compression corpus failed exact roundtrip")
            label = compression_label(result.ratio)
            feature_vector = features.featurize(
                "compressibility_predictor", features.compressibility_values(content)
            )
            # Entropy uses libm.log2; quantize away platform-specific final bits
            # before hashing or training so provenance is stable across CPUs.
            X.append([
                round(float(value), _FEATURE_DECIMALS) for value in feature_vector
            ])
            y.append(_LABELS.index(label))
            evidence.append({
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content_type": content_type,
                "ratio": round(float(result.ratio), 12),
                "label": label,
                "roundtrip": True,
            })
    finally:
        flush_store()
    return np.array(X, dtype=float), np.array(y, dtype=int), evidence


def stratified_split(y, seed: int = 42):
    """Create a deterministic 80/20 holdout with every class represented."""
    rng = np.random.default_rng(seed)
    train, test = [], []
    for class_index in range(len(_LABELS)):
        indices = np.flatnonzero(y == class_index)
        indices = rng.permutation(indices)
        count = max(1, len(indices) // 5)
        test.extend(indices[:count].tolist())
        train.extend(indices[count:].tolist())
    return np.array(sorted(train), dtype=int), np.array(sorted(test), dtype=int)


def train_model(X, y, *, seed: int = 0, epochs: int = 2500, lr: float = 0.01):
    """Train the 6x12x3 network deterministically with Adam.

    Features are standardized for optimization, then the transform is folded
    into the first layer so inference continues to accept the public raw schema.
    """
    rng = np.random.RandomState(seed)
    n_input, n_hidden, n_output = X.shape[1], 12, len(_LABELS)
    targets = np.zeros((len(y), n_output))
    targets[np.arange(len(y)), y] = 1.0
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale < 1e-12] = 1.0
    normalized = (X - mean) / scale
    w1 = rng.randn(n_input, n_hidden) * np.sqrt(2.0 / (n_input + n_hidden))
    b1 = np.zeros(n_hidden)
    w2 = rng.randn(n_hidden, n_output) * np.sqrt(2.0 / (n_hidden + n_output))
    b2 = np.zeros(n_output)
    params = [w1, b1, w2, b2]
    moments = [np.zeros_like(value) for value in params]
    variances = [np.zeros_like(value) for value in params]
    for epoch in range(1, epochs + 1):
        z1 = normalized @ w1 + b1
        hidden = np.maximum(0, z1)
        z2 = hidden @ w2 + b2
        exp = np.exp(z2 - np.max(z2, axis=1, keepdims=True))
        probabilities = exp / np.sum(exp, axis=1, keepdims=True)
        dz2 = (probabilities - targets) / len(normalized)
        dw2 = hidden.T @ dz2
        db2 = np.sum(dz2, axis=0)
        dz1 = (dz2 @ w2.T) * (z1 > 0)
        gradients = [normalized.T @ dz1, np.sum(dz1, axis=0), dw2, db2]
        for index, (parameter, gradient) in enumerate(zip(params, gradients)):
            moments[index] = 0.9 * moments[index] + 0.1 * gradient
            variances[index] = 0.999 * variances[index] + 0.001 * gradient * gradient
            m_hat = moments[index] / (1 - 0.9 ** epoch)
            v_hat = variances[index] / (1 - 0.999 ** epoch)
            parameter -= lr * m_hat / (np.sqrt(v_hat) + 1e-8)
            # BLAS reduction order varies by CPU. Quantizing all optimizer
            # state each step prevents final-bit drift from accumulating.
            parameter[:] = np.round(parameter, _TRAINING_DECIMALS)
            moments[index][:] = np.round(moments[index], _TRAINING_DECIMALS)
            variances[index][:] = np.round(variances[index], _TRAINING_DECIMALS)
    # Fold z = ((x - mean) / scale) @ w1 + b1 into raw-input weights.
    raw_w1 = np.round(w1 / scale[:, None], _TRAINING_DECIMALS)
    raw_b1 = np.round(b1 - (mean / scale) @ w1, _TRAINING_DECIMALS)
    return raw_w1, raw_b1, w2, b2


def predict(X, tensors) -> np.ndarray:
    w1, b1, w2, b2 = tensors
    hidden = np.maximum(0, X @ w1 + b1)
    logits = hidden @ w2 + b2
    return np.argmax(logits, axis=1)


def export_model(tensors) -> dict:
    w1, b1, w2, b2 = tensors
    return {
        "model": "compressibility_predictor",
        "architecture": "feedforward",
        "layers": [6, 12, 3],
        "layer_config": [
            {"name": "hidden", "weights": w1.tolist(), "biases": b1.tolist(), "activation": "relu"},
            {"name": "output", "weights": w2.tolist(), "biases": b2.tolist(), "activation": "softmax"},
        ],
        "num_features": 6,
        "num_classes": 3,
        "labels": _LABELS,
        # Inference format is output-major (out_dim x in_dim), flattened.
        "weights": [w1.T.flatten().tolist(), w2.T.flatten().tolist()],
        "biases": [b1.tolist(), b2.tolist()],
        "activations": ["relu", "softmax"],
    }


def build_provenance(model_data: dict, X, y, evidence, train_idx, test_idx,
                     accuracy: float) -> dict:
    return {
        "maturity": "G1",
        "source_commit": _SOURCE_COMMIT,
        "trainer": _TRAINER,
        "label_contract": {
            "classes": _LABELS,
            "source": "measured universal-compressor output/input ratio after exact reversible roundtrip",
            "thresholds": {"none": ">=0.90", "delta": "0.50-0.90", "heavy": "<0.50"},
            "production_observations": False,
        },
        "corpus": {
            "kind": "embedded_public_deterministic_cases",
            "case_count": len(evidence),
            "content_types": sorted({row["content_type"] for row in evidence}),
            "sha256": _stable_sha256(evidence),
            "raw_content_stored": False,
        },
        "dataset": {
            "samples": int(len(y)),
            "class_counts": np.bincount(y, minlength=3).tolist(),
            "sha256": _stable_sha256({"features": X.tolist(), "labels": y.tolist()}),
            "feature_decimals": _FEATURE_DECIMALS,
        },
        "split": {
            "method": "stratified numpy.default_rng permutation",
            "seed": 42,
            "train_samples": int(len(train_idx)),
            "held_out_samples": int(len(test_idx)),
            "held_out_class_counts": np.bincount(y[test_idx], minlength=3).tolist(),
        },
        "training": {
            "initialization_seed": 0,
            "layers": [6, 12, 3],
            "activations": ["relu", "softmax"],
            "optimizer": "adam",
            "optimizer_state_decimals": _TRAINING_DECIMALS,
            "feature_standardization": "folded_into_first_layer",
            "epochs": 2500,
            "learning_rate": 0.01,
        },
        "evaluation": {
            "metric": "held_out_accuracy",
            "value": accuracy,
            "correct": int(round(accuracy * len(test_idx))),
            "total": int(len(test_idx)),
        },
        "weights": {
            "core_sha256": _stable_sha256(_core_payload(model_data)),
            "reproduction_tolerance_atol": 1e-12,
            "historical_weights_replaced": True,
            "historical_reason": "original trainer did not record an initialization seed",
        },
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    X, y, evidence = build_dataset()
    train_idx, test_idx = stratified_split(y)
    tensors = train_model(X[train_idx], y[train_idx])
    accuracy = float(np.mean(predict(X[test_idx], tensors) == y[test_idx]))
    model = export_model(tensors)
    model["num_samples"] = int(len(y))
    model["accuracy"] = accuracy
    model["trained_on"] = "deterministic_compression_roundtrip_corpus_v1"
    model["provenance"] = build_provenance(
        model, X, y, evidence, train_idx, test_idx, accuracy,
    )
    counts = model["provenance"]["dataset"]["class_counts"]
    print(f"compressibility_predictor: {len(y)} cases, classes={counts}, "
          f"held-out={accuracy:.2%}")
    if "--save" in argv:
        path = _MODELS_DIR / "compressibility_predictor.json"
        path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        print(f"saved {path}")
    return 0 if accuracy >= 0.80 and all(counts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
