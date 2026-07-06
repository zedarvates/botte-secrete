"""Generate bootstrap micro-NN models for Belt 2.0.

Crée des modèles feedforward initialisés avec des poids aléatoires
pour les 7 nouveaux prédicteurs. Ces modèles seront affinés via
l'auto-distillation (P47).
"""
import json
import numpy as np
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

# Architecture pour chaque modèle : (input_features, hidden_units, output_classes)
ARCHITECTURES = {
    "compressibility_predictor":    (6, 12, 3),   # none, delta, heavy
    "context_pruning_predictor":    (6, 12, 2),   # keep, prune
    "skip_agent_predictor":         (7, 14, 2),   # execute, skip
    "cloud_escalation_predictor":   (7, 14, 3),   # local, local_big, cloud
    "response_length_predictor":    (6, 12, 3),   # short, medium, long
    "tool_call_predictor":          (7, 14, 2),   # llm_only, use_tool
    "semantic_cache_hit_predictor": (7, 14, 2),   # miss, hit
}

LABELS = {
    "compressibility_predictor":    ["none", "delta", "heavy"],
    "context_pruning_predictor":    ["keep", "prune"],
    "skip_agent_predictor":         ["execute", "skip"],
    "cloud_escalation_predictor":   ["local_small", "local_big", "cloud"],
    "response_length_predictor":    ["short", "medium", "long"],
    "tool_call_predictor":          ["llm_only", "use_tool"],
    "semantic_cache_hit_predictor": ["miss", "hit"],
}


def make_model(name: str) -> dict:
    """Create an initialized model JSON."""
    n_in, n_hidden, n_out = ARCHITECTURES[name]

    # Xavier initialization
    w1 = np.random.randn(n_in, n_hidden) * np.sqrt(2.0 / (n_in + n_hidden))
    b1 = np.zeros(n_hidden)
    w2 = np.random.randn(n_hidden, n_out) * np.sqrt(2.0 / (n_hidden + n_out))
    b2 = np.zeros(n_out)

    return {
        "model": name,
        "architecture": "feedforward",
        "layers": [n_in, n_hidden, n_out],  # layer sizes for _predict_python
        "layer_config": [                     # detailed layer info
            {
                "name": "hidden",
                "weights": w1.tolist(),
                "biases": b1.tolist(),
                "activation": "relu",
            },
            {
                "name": "output",
                "weights": w2.tolist(),
                "biases": b2.tolist(),
                "activation": "softmax",
            },
        ],
        "num_features": n_in,
        "num_classes": n_out,
        "labels": LABELS[name],
        "num_samples": 0,
        "accuracy": 0.0,
        "generated": "bootstrap",
        # Flat formats for _predict_python compatibility
        "activations": ["relu", "softmax"],
        "weights": [
            w1.flatten().tolist(),   # input → hidden
            w2.flatten().tolist(),   # hidden → output
        ],
        "biases": [
            b1.tolist(),
            b2.tolist(),
        ],
    }


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ARCHITECTURES:
        model = make_model(name)
        path = MODELS_DIR / f"{name}.json"
        path.write_text(json.dumps(model, indent=2))
        print(f"  ✅ {name}: {model['num_features']}f → {model['num_classes']}c → {path}")


if __name__ == "__main__":
    main()
