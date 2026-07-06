"""Checkup — Belt 2.0 : vérifie que les 11 micro-NN sont opérationnels.

Usage:
    python -m skills.auto_router.checkup_belt2
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def check_model(model_name: str) -> dict:
    """Check a single model: file exists, loads, predicts."""
    from skills.botte_nn import features
    from skills.botte_nn.cli import _predict_python, _MODELS_DIR, _MODEL_META

    model_path = _MODELS_DIR / f"{model_name}.json"
    if not model_path.exists():
        return {"model": model_name, "status": "❌", "error": "model file not found"}

    try:
        model_data = json.loads(model_path.read_text())
        meta = _MODEL_META.get(model_name, {})
        n_in = meta.get("input_size", model_data.get("num_features", 0))
        n_out = meta.get("output_size", model_data.get("num_classes", 0))

        # Test prediction with dummy features
        dummy = {s.name: s.lo for s in features.SCHEMAS.get(model_name, [])}
        vec = features.featurize(model_name, dummy)
        probs = _predict_python(str(model_path), vec)

        if not probs or len(probs) != n_out:
            return {"model": model_name, "status": "❌", "error": f"expected {n_out} outputs, got {len(probs or [])}"}

        labels = meta.get("labels", [])
        top_label = labels[max(range(len(probs)), key=probs.__getitem__)] if labels else "?"
        top_conf = max(probs)

        return {
            "model": model_name,
            "status": "✅",
            "features": n_in,
            "classes": n_out,
            "labels": labels,
            "test_prediction": f"{top_label} ({top_conf:.2f})",
            "file_size": f"{model_path.stat().st_size // 1024}KB",
        }
    except Exception as e:
        return {"model": model_name, "status": "❌", "error": str(e)}


def main():
    models = [
        # Belt 1.0
        "binary_router",
        "effort_classifier",
        "anomaly_detector",
        "error_classifier",
        # Belt 2.0
        "compressibility_predictor",
        "context_pruning_predictor",
        "skip_agent_predictor",
        "cloud_escalation_predictor",
        "response_length_predictor",
        "tool_call_predictor",
        "semantic_cache_hit_predictor",
    ]

    print("🧦 Botte Secrète — Micro-NN Belt Checkup")
    print("=" * 60)
    print()
    print(f"{'Modèle':<35} {'État':<5} {'Feat':<6} {'Classes':<10} {'Test':<30}")
    print("-" * 60)

    all_ok = True
    for name in models:
        result = check_model(name)
        status = result["status"]
        if status == "❌":
            all_ok = False

        feats = str(result.get("features", "?"))
        cls = str(result.get("classes", "?"))
        test = result.get("test_prediction", result.get("error", "?"))
        print(f"{name:<35} {status:<5} {feats:<6} {cls:<10} {test:<30}")

    print()
    print(f"Belt 1.0: 4 models | Belt 2.0: 7 models | Total: 11 models")
    print(f"Status: {'✅ ALL OPERATIONAL' if all_ok else '❌ SOME FAILURES'}")


if __name__ == "__main__":
    main()
