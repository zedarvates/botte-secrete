#!/usr/bin/env python3
"""Generate demo models for botte_nn (pre-trained weights).

Produces JSON weight files compatible with the Rust inference engine.

Usage:
    python skills/botte_nn/training/train_model.py

Output:
    models/effort_classifier.json     — 4→12→3 (effort: easy/medium/hard)
    models/binary_router.json         — 3→8→2  (binary: local/cloud)
    models/anomaly_detector.json      — 5→10→2  (normal/anomaly)
"""

import json
import sys
from pathlib import Path

import numpy as np

# Add parent to path for training module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import TinyNN


_SEED = 42
_EPOCHS = 2000
_LR = 0.01
_SAMPLES = 5000


def _class_weight(labels):
    # DEAD CODE: unused function
    """Normalize class distribution."""
    counts = np.sum(labels, axis=0)
    total = len(labels)
    weights = total / (len(counts) * counts)
    return weights / weights.mean()


def generate_effort_classifier():
    """4 features → 3 classes (easy/medium/hard).

    Features:
        [0] file_size_ratio: 0.0-1.0 (relative to 100KB)
        [1] token_ratio: 0.0-1.0 (tokens / 2000)
        [2] is_code: 0 or 1
        [3] depth_ratio: 0.0-1.0 (directory depth / 10)

    Classes:
        0 = easy (local model), 1 = medium (hybrid), 2 = hard (cloud)
    """
    print("🧪 Generating effort_classifier...")
    np.random.seed(_SEED)

    X = np.random.rand(_SAMPLES, 4)
    y = np.zeros((_SAMPLES, 3), dtype=float)

    for i in range(_SAMPLES):
        score = (X[i, 0] * 2.0 + X[i, 1] * 3.0 + X[i, 2] * 0.5 - X[i, 3] * 0.5)
        # Add noise
        score += np.random.randn() * 0.2
        thresh = score - score.min()
        if thresh < 0.33:
            y[i, 0] = 1
        elif thresh < 0.66:
            y[i, 1] = 1
        else:
            y[i, 2] = 1

    model = TinyNN([4, 12, 3], ["relu", "softmax"])
    model.train(X, y, epochs=_EPOCHS, lr=_LR)

    data = model.export_json()
    path = Path("models/effort_classifier.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    # Verify
    verify = model.predict(X[:10])
    preds = verify.argmax(axis=1)
    truth = y[:10].argmax(axis=1)
    acc = np.mean(preds == truth)
    print(f"  ✅ Saved to {path}  (sample accuracy: {acc:.2%})")
    return path


def generate_binary_router():
    """3 features → 2 classes (local/cloud).

    Features:
        [0] task_complexity: 0.0-1.0
        [1] token_budget_ratio: 0.0-1.0 (budget remaining / total)
        [2] has_local_model: 0 or 1

    Classes:
        0 = local, 1 = cloud
    """
    print("🧪 Generating binary_router...")
    np.random.seed(_SEED + 1)

    X = np.random.rand(_SAMPLES, 3)
    y = np.zeros((_SAMPLES, 2), dtype=float)

    for i in range(_SAMPLES):
        # Cloud if: complex AND (no local model OR budget exhausted)
        should_cloud = (X[i, 0] > 0.6 and (X[i, 2] < 0.5 or X[i, 1] < 0.3))
        if np.random.rand() < 0.1:  # 10% noise
            should_cloud = not should_cloud
        y[i, 0 if not should_cloud else 1] = 1

    model = TinyNN([3, 8, 2], ["relu", "softmax"])
    model.train(X, y, epochs=_EPOCHS, lr=_LR)

    data = model.export_json()
    path = Path("models/binary_router.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    verify = model.predict(X[:10])
    preds = verify.argmax(axis=1)
    truth = y[:10].argmax(axis=1)
    acc = np.mean(preds == truth)
    print(f"  ✅ Saved to {path}  (sample accuracy: {acc:.2%})")
    return path


def generate_anomaly_detector():
    """5 features → 2 classes (normal/anomaly).

    Features:
        [0] log_freq: log entries per minute (normalized)
        [1] error_ratio: ratio of error lines
        [2] unique_errors: unique error types / 10
        [3] avg_latency: request latency / 1000ms
        [4] retry_count: retries / 5

    Classes:
        0 = normal, 1 = anomaly
    """
    print("🧪 Generating anomaly_detector...")
    np.random.seed(_SEED + 2)

    X = np.random.rand(_SAMPLES, 5)
    y = np.zeros((_SAMPLES, 2), dtype=float)

    for i in range(_SAMPLES):
        # Anomaly if: high errors AND (high latency OR many retries)
        is_anomaly = (X[i, 1] > 0.6 and (X[i, 3] > 0.7 or X[i, 4] > 0.6))
        if np.random.rand() < 0.05:  # 5% noise
            is_anomaly = not is_anomaly
        y[i, 0 if not is_anomaly else 1] = 1

    model = TinyNN([5, 10, 2], ["relu", "softmax"])
    model.train(X, y, epochs=_EPOCHS, lr=_LR)

    data = model.export_json()
    path = Path("models/anomaly_detector.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    verify = model.predict(X[:10])
    preds = verify.argmax(axis=1)
    truth = y[:10].argmax(axis=1)
    acc = np.mean(preds == truth)
    print(f"  ✅ Saved to {path}  (sample accuracy: {acc:.2%})")
    return path


def main():
    print("=" * 50)
    print("🧠 botte_nn — Model Training")
    print("=" * 50)
    generate_effort_classifier()
    generate_binary_router()
    generate_anomaly_detector()
    print("\n✅ All models generated in models/")


if __name__ == "__main__":
    main()
