#!/usr/bin/env python3
"""Train error_classifier — classifie le type d'erreur pour auto-recovery.

Features (12) :
    [0]  error_code_norm      — code de sortie / 255
    [1]  message_length_ratio — longueur message / 2000
    [2]  has_traceback        — 0 ou 1
    [3]  kw_syntax            — SyntaxError, invalid syntax, EOL...
    [4]  kw_runtime           — TypeError, ValueError, KeyError...
    [5]  kw_network           — ConnectionError, timeout, DNS...
    [6]  kw_permission        — Permission denied, Access denied...
    [7]  kw_timeout           — timeout, TimeoutError, deadline...
    [8]  kw_resource          — MemoryError, OOM, disk full...
    [9]  line_count_ratio     — nb lignes d'erreur / 100
    [10] has_suggestion       — "did you mean?" ou suggestion
    [11] exit_code_nonzero    — 0 ou 1

Classes (6) :
    0 = syntax_error
    1 = runtime_error
    2 = network_error
    3 = permission_error
    4 = timeout_error
    5 = resource_error

Usage :
    python skills/botte_nn/training/train_error_classifier.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import TinyNN

SEED = 42
EPOCHS = 3000
LR = 0.005
SAMPLES = 8000


def generate_data(n: int = 8000) -> tuple[np.ndarray, np.ndarray]:
    np.random.seed(SEED)
    X = np.zeros((n, 12))
    y = np.zeros((n, 6), dtype=float)

    profiles = [
        (0, 1, 0.8, 0.3, 1, 0, 0, 0, 0, 0.6, 0.3, 1),   # syntax
        (1, 0, 0.6, 0.7, 0, 1, 0, 0, 0, 0.4, 0.1, 1),   # runtime
        (2, 0, 0.9, 0.5, 0, 0, 1, 0, 0, 0.3, 0, 1),      # network
        (3, 1, 0.5, 0.2, 0, 0, 0, 1, 0, 0.2, 0, 1),      # permission
        (4, 0, 0.4, 0.8, 0, 0, 1, 0, 0, 0.5, 0, 1),      # timeout
        (5, 1, 0.3, 0.9, 0, 0, 0, 0, 1, 0.2, 0, 1),      # resource
    ]

    for i in range(n):
        cls = np.random.randint(0, 6)
        prof = profiles[cls]

        X[i, 0] = max(0, min(1, prof[1] + np.random.randn() * 0.15))
        X[i, 1] = max(0, min(1, prof[2] + np.random.randn() * 0.15))
        for j in range(2, 12):
            X[i, j] = 1.0 if np.random.rand() < prof[j] else 0.0

        # Ajouter du bruit : des mots-clés d'autres classes
        for other_cls in range(6):
            if other_cls != cls and np.random.rand() < 0.1:
                for j in range(3, 9):
                    oprof = profiles[other_cls]
                    if oprof[j] == 1 and np.random.rand() < 0.3:
                        X[i, j] = 1.0

        y[i, cls] = 1

    return X, y


def main():
    print("🧪 Training error_classifier...")
    X, y = generate_data(SAMPLES)

    model = TinyNN([12, 16, 6], ["relu", "softmax"])
    model.train(X, y, epochs=EPOCHS, lr=LR)

    preds = model.predict(X)
    acc = np.mean(preds.argmax(axis=1) == y.argmax(axis=1))
    print(f"\n  ✅ Accuracy: {acc:.2%}")

    models_dir = Path(__file__).resolve().parents[1] / "models"
    save_path = models_dir / "error_classifier.json"
    data = model.export_json()
    with open(save_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✅ Saved to {save_path}")

    labels = ["syntax", "runtime", "network", "permission", "timeout", "resource"]
    tests = [
        ([1, 0.3, 1, 1,0,0,0,0,0, 0.6, 0.3, 1], "SyntaxError: invalid syntax"),
        ([0, 0.7, 1, 0,1,0,0,0,0, 0.4, 0.1, 1], "TypeError: unsupported operand"),
        ([0, 0.5, 1, 0,0,1,0,0,0, 0.3, 0, 1],  "ConnectionError: connection refused"),
        ([1, 0.2, 0, 0,0,0,1,0,0, 0.2, 0, 1],  "Permission denied: /etc/shadow"),
        ([0, 0.8, 1, 0,0,1,0,0,0, 0.5, 0, 1],  "TimeoutError: operation timed out"),
        ([1, 0.9, 0, 0,0,0,0,0,1, 0.2, 0, 1],  "MemoryError: out of memory"),
    ]
    print("\n  🧪 Tests:")
    for feat, desc in tests:
        out = model.predict(np.array([feat]))
        cls = out.argmax(axis=1)[0]
        print(f"    {labels[cls]:<12} ({out[0][cls]:.1%})  ← {desc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
