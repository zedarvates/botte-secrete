#!/usr/bin/env python3
"""Train token_estimator — prédire la consommation de tokens AVANT d'exécuter.

Features (14) :
    [0]  prompt_length_ratio  — longueur du prompt / 8000
    [1-6] task_type           — one-hot (code, reasoning, creative, analysis, search, simple)
    [7-10] target_model       — one-hot (local_small, local_medium, cloud_small, cloud_large)
    [11] complexity           — 0.0-1.0 (de effort_classifier ou heuristique)
    [12] has_context          — 0 ou 1 (historique de conversation)
    [13] expected_depth       — 0.0-1.0 (nombre d'étapes de raisonnement / 10)

Classes (3) :
    0 = LOW (< 500 tokens)
    1 = MEDIUM (500-2000 tokens)
    2 = HIGH (> 2000 tokens)

Usage :
    python skills/botte_nn/training/train_token_estimator.py
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
    """Génère des données d'entraînement synthétiques réalistes.

    Basé sur des heuristiques de consommation réelle de tokens.
    """
    np.random.seed(SEED)
    X = np.zeros((n, 14))
    y = np.zeros((n, 3), dtype=float)

    # Types de tâche et leur consommation typique
    task_type_profiles = {
        "code": (0.6, 0.9, 0.7, 0.6),       # (avg_prompt, avg_context, avg_depth, base_tokens)
        "reasoning": (0.4, 0.7, 0.8, 0.7),
        "creative": (0.3, 0.3, 0.4, 0.5),
        "analysis": (0.5, 0.8, 0.6, 0.6),
        "search": (0.2, 0.1, 0.1, 0.2),
        "simple": (0.1, 0.0, 0.0, 0.1),
    }

    task_types = list(task_type_profiles.keys())

    for i in range(n):
        # Sélectionner un type de tâche aléatoire
        t_idx = np.random.randint(0, 6)
        t_name = task_types[t_idx]
        profile = task_type_profiles[t_name]

        # Features
        X[i, 0] = max(0.05, min(1.0, profile[0] + np.random.randn() * 0.15))  # prompt_length

        # One-hot task type
        X[i, 1 + t_idx] = 1.0

        # Modèle cible (biaisé vers local)
        model_idx = np.random.choice(4, p=[0.4, 0.3, 0.2, 0.1])
        X[i, 7 + model_idx] = 1.0

        # Complexité
        X[i, 11] = max(0.05, min(1.0, profile[1] + np.random.randn() * 0.2))

        # Contexte
        X[i, 12] = 1.0 if np.random.rand() < profile[2] else 0.0

        # Profondeur attendue
        X[i, 13] = max(0.0, min(1.0, profile[3] + np.random.randn() * 0.2))

        # Calculer le score de consommation (règle heuristique)
        base = profile[0] * 0.3 + X[i, 11] * 0.3 + X[i, 13] * 0.2 + X[i, 12] * 0.1
        # Ajustement selon le modèle
        if model_idx >= 2:  # cloud
            base += 0.2
        if model_idx == 3:  # cloud large
            base += 0.2
        # Ajustement selon la longueur du prompt
        base += X[i, 0] * 0.2

        # Ajouter du bruit
        base += np.random.randn() * 0.1
        base = max(0.0, min(1.0, base))

        # Assigner la classe
        if base < 0.3:
            y[i, 0] = 1  # LOW
        elif base < 0.6:
            y[i, 1] = 1  # MEDIUM
        else:
            y[i, 2] = 1  # HIGH

    return X, y


def main():
    print("🧪 Training token_estimator...")
    print(f"  Samples: {SAMPLES}, Epochs: {EPOCHS}, LR: {LR}")
    print()

    # Data
    X, y = generate_training_data(SAMPLES)

    # Modèle : 14 entrées → 12 cachées → 3 sorties (softmax)
    model = TinyNN([14, 12, 3], ["relu", "softmax"])

    # Entraînement
    model.train(X, y, epochs=EPOCHS, lr=LR)

    # Validation
    preds = model.predict(X)
    predicted_classes = preds.argmax(axis=1)
    true_classes = y.argmax(axis=1)
    accuracy = np.mean(predicted_classes == true_classes)
    print(f"\n  ✅ Accuracy: {accuracy:.2%}")

    # Distribution des classes
    unique, counts = np.unique(predicted_classes, return_counts=True)
    dist = dict(zip(["LOW", "MEDIUM", "HIGH"], [0, 0, 0]))
    for u, c in zip(unique, counts):
        dist[["LOW", "MEDIUM", "HIGH"][u]] = c
    print(f"  Distribution prédite: {dist}")

    # Export
    models_dir = Path(__file__).resolve().parents[1] / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    save_path = models_dir / "token_estimator.json"

    data = model.export_json()
    with open(save_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  ✅ Model saved to {save_path}")

    # Test avec des cas concrets
    print("\n  🧪 Tests concrets:")
    test_cases = [
        ([0.1, 0,0,0,0,0,1, 1,0,0,0, 0.2, 0, 0.1], "simple/0 → LOW"),
        ([0.5, 0,0,1,0,0,0, 0,1,0,0, 0.7, 1, 0.8], "reasoning+context → HIGH"),
        ([0.8, 1,0,0,0,0,0, 0,0,0,1, 0.9, 1, 0.9], "code+cloud+context → HIGH"),
        ([0.2, 0,0,0,0,1,0, 1,0,0,0, 0.3, 0, 0.1], "search+local → LOW"),
        ([0.4, 0,1,0,0,0,0, 0,1,0,0, 0.5, 0, 0.4], "creative+medium → MEDIUM"),
    ]

    for features, desc in test_cases:
        inp = np.array([features])
        out = model.predict(inp)
        cls = out.argmax(axis=1)[0]
        labels = ["LOW", "MEDIUM", "HIGH"]
        print(f"    {labels[cls]:<8} ({out[0][cls]:.1%})  ← {desc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
