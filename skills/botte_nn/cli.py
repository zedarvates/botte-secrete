#!/usr/bin/env python3
"""botton_nn — CLI Python pour inference tiny neural network Rust.

Utilise soit:
1. Le binaire Rust compilé (botte_nn_cli) — rapide, 0 dépendance
2. Fallback Python (numpy) — si le binaire Rust n'est pas compilé

Usage:
    python -m skills.botte_nn.cli predict models/effort_classifier.json \\
        --input 0.5 0.3 0.8 0.1

    python -m skills.botte_nn.cli predict models/binary_router.json \\
        --input 0.7 0.2 0.5 --probabilities

    python -m skills.botte_nn.cli which \\
        --input 0.1 0.2 0.8 0.0  # classify + label

    python -m skills.botte_nn.cli list  # list available models
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


_MODELS_DIR = Path(__file__).resolve().parent / "models"
_RUST_BINARY = Path(__file__).resolve().parent.parent / "botte_nn" / "target" / "release" / "botte_nn_cli"

# ── Model metadata ──
_MODEL_META = {
    "effort_classifier": {
        "path": "effort_classifier.json",
        "input_size": 4,
        "output_size": 3,
        "labels": ["easy (local)", "medium (hybrid)", "hard (cloud)"],
        "description": "Classify task effort from file size, tokens, code-ness, depth",
    },
    "binary_router": {
        "path": "binary_router.json",
        "input_size": 3,
        "output_size": 2,
        "labels": ["local", "cloud"],
        "description": "Route task: local or cloud based on complexity, budget, local model",
    },
    "anomaly_detector": {
        "path": "anomaly_detector.json",
        "input_size": 5,
        "output_size": 2,
        "labels": ["normal", "anomaly"],
        "description": "Detect log anomalies: error ratio, latency, retries",
    },
    "token_estimator": {
        "path": "token_estimator.json",
        "input_size": 14,
        "output_size": 3,
        "labels": ["low (<500)", "medium (500-2000)", "high (>2000)"],
        "description": "Estimate token consumption before execution: prompt length, task type, target model, context",
    },
    "priority_estimator": {
        "path": "priority_estimator.json",
        "input_size": 12,
        "output_size": 3,
        "labels": ["low", "normal", "high"],
        "description": "Prioritize tasks in queue: urgency, dependencies, wait time, user tier, deadline",
    },
    "error_classifier": {
        "path": "error_classifier.json",
        "input_size": 12,
        "output_size": 6,
        "labels": ["syntax", "runtime", "network", "permission", "timeout", "resource"],
        "description": "Classify error type for auto-recovery: syntax, runtime, network, permission, timeout, resource",
    },
}


def _find_model(name_or_path: str) -> dict | None:
    """Find model by name or path. Returns metadata dict with resolved path."""
    # Try name
    if name_or_path in _MODEL_META:
        meta = dict(_MODEL_META[name_or_path])
        p = _MODELS_DIR / meta["path"]
        if p.exists():
            meta["path"] = str(p)
            return meta
        return None

    # Try as file path
    p = Path(name_or_path)
    if p.exists():
        # Load the model JSON to infer metadata
        with open(p) as f:
            data = json.load(f)
        return {
            "path": str(p),
            "input_size": data["layers"][0],
            "output_size": data["layers"][-1],
            "labels": [f"class_{i}" for i in range(data["layers"][-1])],
            "description": "Custom model",
        }
    return None


def _predict_rust(binary: str, model_json: str, input_vec: list[float]) -> list[float]:
    """Predict using Rust binary (subprocess)."""
    result = subprocess.run(
        [binary, "--model", model_json, "--input"] + [str(x) for x in input_vec],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rust binary error: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


def _predict_python(model_json: str, input_vec: list[float]) -> list[float]:
    """Fallback prediction using Python/numpy."""
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("numpy required for Python fallback prediction. "
                           "Install with: pip install numpy")

    with open(model_json) as f:
        data = json.load(f)

    layers = data["layers"]
    weights = [np.array(w, dtype=float) for w in data["weights"]]  # flat row-major
    biases = [np.array(b, dtype=float) for b in data["biases"]]
    activations = data["activations"]

    def _softmax(x):
        e = np.exp(x - np.max(x))
        return e / np.sum(e)

    def _relu(x):
        return np.maximum(0, x)

    def _sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

    h = np.array(input_vec, dtype=float)
    for i in range(len(weights)):
        # weights are flat row-major: output_size × input_size
        # Reshape to (output_size, input_size) for matmul
        out_dim = layers[i + 1]
        in_dim = layers[i]
        w_mat = weights[i].reshape(out_dim, in_dim)
        z = h @ w_mat.T + biases[i]
        act = activations[i]
        if act == "relu":
            h = _relu(z)
        elif act == "sigmoid":
            h = _sigmoid(z)
        elif act == "softmax":
            h = _softmax(z)
        # linear = identity

    return h.tolist()


def do_predict(args):
    """Predict using Rust binary or Python fallback."""
    meta = _find_model(args.model)
    if not meta:
        print(f"❌ Model not found: {args.model}", file=sys.stderr)
        available = list(_MODEL_META.keys())
        print(f"   Available: {', '.join(available)}", file=sys.stderr)
        return 1

    input_vec = args.input
    expected = meta["input_size"]
    if len(input_vec) != expected:
        print(f"❌ Expected {expected} inputs, got {len(input_vec)}", file=sys.stderr)
        return 1

    # Try Rust first, fallback to Python
    try:
        if _RUST_BINARY.exists():
            output = _predict_rust(str(_RUST_BINARY), meta["path"], input_vec)
        else:
            output = _predict_python(meta["path"], input_vec)
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"⚠️  Rust binary failed, using Python fallback: {e}", file=sys.stderr)
        try:
            output = _predict_python(meta["path"], input_vec)
        except Exception as e2:
            print(f"❌ Python fallback also failed: {e2}", file=sys.stderr)
            return 1

    if args.probabilities:
        for i, (label, prob) in enumerate(zip(meta["labels"], output)):
            bar = "█" * int(prob * 20) + "░" * (20 - int(prob * 20))
            print(f"  {i}: {label:<20} [{bar}] {prob:.4f}")
    elif args.json:
        print(json.dumps({
            "model": args.model,
            "input": input_vec,
            "output": output,
            "labels": meta["labels"],
        }, indent=2))
    else:
        pred_class = output.index(max(output))
        print(f"  Input: {input_vec}")
        print(f"  Prediction: {meta['labels'][pred_class]} (confidence: {max(output):.4f})")

    return 0


def do_which(args):
    """Classify input and return the best label."""
    # Try each model
    best_label = None
    best_conf = 0.0

    for name, meta in _MODEL_META.items():
        if len(args.input) != meta["input_size"]:
            continue
        try:
            output = _predict_python(str(_MODELS_DIR / meta["path"]), args.input)
            conf = max(output)
            if conf > best_conf:
                best_conf = conf
                best_label = meta["labels"][output.index(max(output))]
        except Exception:
            continue

    if best_label:
        if args.json:
            print(json.dumps({"label": best_label, "confidence": best_conf}))
        else:
            print(f"  🧠 {best_label} (confidence: {best_conf:.2%})")
    else:
        print("  ❓ No model matches the input dimensions")
    return 0


def do_list(args):
    """List available models."""
    print("Available models:")
    print(f"{'Name':<20} {'Inputs':<8} {'Outputs':<8} {'Description'}")
    print("-" * 70)
    for name, meta in _MODEL_META.items():
        p = _MODELS_DIR / meta["path"]
        status = "✅" if p.exists() else "❌"
        print(f"  {status} {name:<18} {meta['input_size']:<8} {meta['output_size']:<8} {meta['description']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="botte_nn", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("predict", help="Run inference on a model")
    s.add_argument("model", help="Model name or path to JSON weights")
    s.add_argument("--input", type=float, nargs="+", required=True,
                   help="Input features")
    s.add_argument("--probabilities", action="store_true",
                   help="Show per-class probabilities")
    s.add_argument("--json", action="store_true",
                   help="Output as JSON")

    s = sub.add_parser("which", help="Classify input across all models")
    s.add_argument("--input", type=float, nargs="+", required=True)
    s.add_argument("--json", action="store_true")

    sub.add_parser("list", help="List available models")

    args = p.parse_args(argv)

    if args.cmd == "predict":
        return do_predict(args)
    elif args.cmd == "which":
        return do_which(args)
    elif args.cmd == "list":
        return do_list(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
