#!/usr/bin/env python3
"""Train a tiny feedforward neural network with numpy.

Usage:
    python skills/botte_nn/training/train.py \
        --layers 4 16 3 \
        --epochs 200 \
        --lr 0.01 \
        --save models/effort_classifier.json

This produces a JSON file compatible with botte_nn Rust inference.
No external ML dependencies — only numpy.
"""

import json
import argparse
import sys
from pathlib import Path

import numpy as np


def relu(x):
    return np.maximum(0, x)


def relu_deriv(x):
    return (x > 0).astype(float)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))


def sigmoid_deriv(x):
    s = sigmoid(x)
    return s * (1 - s)


def softmax(x):
    e = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e / np.sum(e, axis=-1, keepdims=True)


# Activation map
ACTIVATIONS = {
    "relu": (relu, relu_deriv),
    "sigmoid": (sigmoid, sigmoid_deriv),
    "softmax": (None, None),  # handled separately
    "linear": (lambda x: x, lambda x: np.ones_like(x)),
}


class TinyNN:
    """Tiny feedforward neural network compatible with botte_nn Rust export."""

    def __init__(self, layers, activations):
        """
        Args:
            layers: list of ints [input_dim, hidden1, ..., output_dim]
            activations: list of str per layer (excl. input)
        """
        assert len(layers) >= 2
        assert len(activations) == len(layers) - 1

        self.layers = layers
        self.activations = activations
        self.weights = []
        self.biases = []

        # Xavier init
        for i in range(len(layers) - 1):
            in_dim = layers[i]
            out_dim = layers[i + 1]
            limit = np.sqrt(6.0 / (in_dim + out_dim))
            self.weights.append(np.random.uniform(-limit, limit, (in_dim, out_dim)))
            self.biases.append(np.zeros(out_dim))

    @classmethod
    def from_json_data(cls, data):
        """Build a model pre-loaded with exported weights (warm start).

        Inverse of export_json: the flat weight arrays are row-major
        (out_dim, in_dim); internal matrices are (in_dim, out_dim).
        """
        model = cls(data["layers"], data["activations"])
        for i, (flat, bias) in enumerate(zip(data["weights"], data["biases"])):
            out_dim = data["layers"][i + 1]
            in_dim = data["layers"][i]
            w_oi = np.array(flat, dtype=float).reshape(out_dim, in_dim)
            model.weights[i] = w_oi.T.copy()       # → (in_dim, out_dim)
            model.biases[i] = np.array(bias, dtype=float)
        return model

    def forward(self, x):
        """Forward pass. Returns (output, layer_outputs) for backprop."""
        layer_outputs = []
        h = x
        for i in range(len(self.weights)):
            z = h @ self.weights[i] + self.biases[i]
            act = self.activations[i]
            if act == "softmax":
                h = softmax(z)
            else:
                fn, _ = ACTIVATIONS[act]
                h = fn(z)
            layer_outputs.append((z, h))
        return h, layer_outputs

    def predict(self, x):
        """Forward pass only (for inference)."""
        h = x
        for i in range(len(self.weights)):
            z = h @ self.weights[i] + self.biases[i]
            act = self.activations[i]
            if act == "softmax":
                h = softmax(z)
            else:
                fn, _ = ACTIVATIONS[act]
                h = fn(z)
        return h

    def train(self, X, y, epochs=100, lr=0.01, verbose=True):
        """Train using SGD + MSE loss."""
        n = len(X)
        for epoch in range(epochs):
            # Forward
            output, layer_outputs = self.forward(X)

            # MSE loss
            loss = np.mean((output - y) ** 2)

            # Backprop
            dL = 2 * (output - y) / n  # derivative of MSE

            for i in reversed(range(len(self.weights))):
                z, h = layer_outputs[i]
                act = self.activations[i]

                if act == "softmax":
                    # simplified: softmax + cross-entropy approximation
                    dA = dL
                else:
                    _, deriv_fn = ACTIVATIONS[act]
                    dA = dL * deriv_fn(z)

                if i == 0:
                    h_prev = X
                else:
                    _, h_prev = layer_outputs[i - 1]

                dW = h_prev.T @ dA
                db = np.sum(dA, axis=0)

                # Propagate gradient
                dL = dA @ self.weights[i].T

                # Update
                self.weights[i] -= lr * dW
                self.biases[i] -= lr * db

            if verbose and (epoch + 1) % max(1, epochs // 10) == 0:
                acc = np.mean((output.argmax(axis=1) == y.argmax(axis=1))) if y.ndim > 1 and y.shape[1] > 1 else 0
                print(f"  Epoch {epoch+1}/{epochs}  loss={loss:.6f}  acc={acc:.3f}")

    def export_json(self):
        """Export weights in botte_nn Rust-compatible JSON format."""
        data = {
            "layers": self.layers,
            "weights": [np.concatenate(w.T).tolist() for w in self.weights],  # Rust: row-major flat
            "biases": [b.tolist() for b in self.biases],
            "activations": self.activations,
        }
        return data


def main():
    p = argparse.ArgumentParser(description="Train a tiny NN for Botte Secrète")
    p.add_argument("--layers", type=int, nargs="+", default=[4, 16, 3],
                   help="Layer sizes: input hidden1 ... output")
    p.add_argument("--activations", nargs="+",
                   default=["relu", "relu", "softmax"],
                   help="Activations per hidden+output layer")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--lr", type=float, default=0.01)
    p.add_argument("--samples", type=int, default=1000,
                   help="Training samples to generate")
    p.add_argument("--save", default=None,
                   help="Save model JSON to path")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--demo", action="store_true",
                   help="Train with demo data (effort classification)")
    args = p.parse_args()

    np.random.seed(args.seed)

    if args.demo:
        print("🧪 Training demo: effort classifier (4 features → 3 classes)")
        # Synthetic data: [file_size_ratio, token_count/1000, is_code, depth/10]
        X = np.random.rand(args.samples, 4)
        # Simple rules for demo:
        # class 0: easy (local) - small files, few tokens
        # class 1: medium (hybrid)
        # class 2: hard (cloud) - large files, lots of tokens
        y_scores = (X[:, 0] * 2 + X[:, 1] * 3 + X[:, 2] * 0.5 - X[:, 3])
        y_scores = y_scores - y_scores.min()
        y_scores = y_scores / y_scores.max()
        y = np.zeros((args.samples, 3))
        for i in range(args.samples):
            if y_scores[i] < 0.33:
                y[i, 0] = 1
            elif y_scores[i] < 0.66:
                y[i, 1] = 1
            else:
                y[i, 2] = 1

        args.layers = [4, 12, 3]
        args.activations = ["relu", "relu", "softmax"]
    else:
        X = np.random.randn(args.samples, args.layers[0])
        y = np.random.rand(args.samples, args.layers[-1])

    model = TinyNN(args.layers, args.activations)
    print(f"  Model: {args.layers}, activations={args.activations}")
    print(f"  Training on {args.samples} samples, {args.epochs} epochs...")
    model.train(X, y, epochs=args.epochs, lr=args.lr)

    # Test a prediction
    test = X[:3]
    pred = model.predict(test)
    print(f"\n  Sample predictions: {pred}")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = model.export_json()
        with open(save_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Model saved to {save_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
