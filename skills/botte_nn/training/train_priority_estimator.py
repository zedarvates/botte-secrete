#!/usr/bin/env python3
"""Train priority_estimator — prioriser les tâches dans la file d'attente.

Features (12) :
    [0]  urgency             — 0.0-1.0 (mots-clés: urgent/critical/bug)
    [1]  dependencies_count  — 0.0-1.0 (dépendances bloquantes / 10)
    [2]  wait_time_ratio     — 0.0-1.0 (temps d'attente / seuil)
    [3-8] task_type          — one-hot (code, fix, review, security, search, report)
    [9]  user_tier           — 0 ou 1 (payant ou pas)
    [10] has_deadline        — 0 ou 1
    [11] complexity          — 0.0-1.0 (de effort_classifier)

Classes (3) :
    0 = LOW priority
    1 = NORMAL priority
    2 = HIGH priority

Usage :
    python skills/botte_nn/training/train_priority_estimator.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import TinyNN

SEED = 42
EPOCHS = 2000
LR = 0.005
SAMPLES = 5000


def generate_training_data(n: int = 5000) -> tuple[np.ndarray, np.ndarray]:
    np.random.seed(SEED)
    X = np.zeros((n, 12))
    y = np.zeros((n, 3), dtype=float)

    task_profiles = {
        "code": (0.3, 0.4, 0.4, 0.5),
        "fix": (0.8, 0.3, 0.6, 0.7),
        "review": (0.3, 0.2, 0.4, 0.4),
        "security": (0.9, 0.1, 0.7, 0.8),
        "search": (0.2, 0.0, 0.2, 0.2),
        "report": (0.1, 0.1, 0.3, 0.3),
    }
    task_types = list(task_profiles.keys())

    for i in range(n):
        t_idx = np.random.randint(0, 6)
        t_name = task_types[t_idx]
        profile = task_profiles[t_name]

        X[i, 0] = max(0.0, min(1.0, profile[0] + np.random.randn() * 0.2))
        X[i, 1] = max(0.0, min(1.0, np.random.beta(1, 3)))
        X[i, 2] = max(0.0, min(1.0, np.random.beta(2, 2)))
        X[i, 3 + t_idx] = 1.0
        X[i, 9] = 1.0 if np.random.rand() < 0.3 else 0.0
        X[i, 10] = 1.0 if np.random.rand() < profile[2] else 0.0
        X[i, 11] = max(0.0, min(1.0, profile[3] + np.random.randn() * 0.2))

        score = (
            X[i, 0] * 0.35 +
            X[i, 1] * 0.15 +
            X[i, 2] * 0.10 +
            X[i, 9] * 0.15 +
            X[i, 10] * 0.15 +
            X[i, 11] * 0.10 +
            np.random.randn() * 0.1
        )
        score = max(0.0, min(1.0, score))

        if score < 0.3:
            y[i, 0] = 1
        elif score < 0.6:
            y[i, 1] = 1
        else:
            y[i, 2] = 1

    return X, y


def main():
    print("🧪 Training priority_estimator...")
    X, y = generate_training_data(SAMPLES)

    model = TinyNN([12, 12, 3], ["relu", "softmax"])
    model.train(X, y, epochs=EPOCHS, lr=LR)

    preds = model.predict(X)
    acc = np.mean(preds.argmax(axis=1) == y.argmax(axis=1))
    print(f"\n  ✅ Accuracy: {acc:.2%}")

    models_dir = Path(__file__).resolve().parents[1] / "models"
    save_path = models_dir / "priority_estimator.json"
    data = model.export_json()
    with open(save_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✅ Saved to {save_path}")

    # Tests concrets
    labels = ["LOW", "NORMAL", "HIGH"]
    test_cases = [
        ([0.9, 0.0, 0.1, 0,0,0,0,0,1, 1, 1, 0.8], "security+urgent+payant → HIGH"),
        ([0.2, 0.1, 0.2, 0,0,0,0,1,0, 0, 0, 0.2], "search+simple → LOW"),
        ([0.5, 0.4, 0.5, 0,1,0,0,0,0, 0, 1, 0.5], "fix+deadline → NORMAL"),
    ]
    print("\n  🧪 Tests:")
    for features, desc in test_cases:
        out = model.predict(np.array([features]))
        cls = out.argmax(axis=1)[0]
        print(f"    {labels[cls]:<8} ({out[0][cls]:.1%})  ← {desc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
