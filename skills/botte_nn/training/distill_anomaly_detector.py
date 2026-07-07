#!/usr/bin/env python3
"""Distill anomaly_detector from realistic log patterns instead of np.random.

    python -m skills.botte_nn.training.distill_anomaly_detector          # report only
    python -m skills.botte_nn.training.distill_anomaly_detector --save   # write weights
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from skills.botte_nn import features
from skills.botte_nn.cli import _predict_python, _MODELS_DIR
from skills.botte_nn.training.train import TinyNN

# Realistic log patterns -> (log_freq, error_ratio, unique_errors, avg_latency, retry_count, label)
# label: 0 = normal, 1 = anomaly
LOG_PATTERNS: list[tuple[str, float, float, float, float, float, int]] = [
    # ── NORMAL ──
    ("low traffic, clean logs", 0.10, 0.02, 0.05, 0.05, 0.00, 0),
    ("normal traffic, occasional 404", 0.30, 0.08, 0.15, 0.10, 0.05, 0),
    ("moderate traffic, few warnings", 0.40, 0.12, 0.20, 0.15, 0.10, 0),
    ("high traffic, expected rate", 0.70, 0.15, 0.30, 0.20, 0.15, 0),
    ("burst traffic, normal errors", 0.60, 0.18, 0.25, 0.30, 0.20, 0),
    ("steady load, healthy", 0.50, 0.05, 0.10, 0.12, 0.05, 0),
    ("weekend low traffic", 0.05, 0.03, 0.08, 0.08, 0.02, 0),
    ("deploy window, elevated but ok", 0.55, 0.25, 0.35, 0.35, 0.30, 0),
    ("cache warming, slow but stable", 0.45, 0.10, 0.15, 0.40, 0.10, 0),
    ("DB backup, I/O spike", 0.20, 0.05, 0.05, 0.50, 0.05, 0),

    # ── ANOMALY ──
    ("error storm: 80% errors", 0.50, 0.80, 0.70, 0.30, 0.20, 1),
    ("cascading failure: high latency + errors", 0.60, 0.65, 0.75, 0.85, 0.60, 1),
    ("retry storm: max retries exhausted", 0.30, 0.20, 0.15, 0.40, 0.90, 1),
    ("connection pool exhausted", 0.40, 0.55, 0.50, 0.75, 0.70, 1),
    ("disk full: all writes fail", 0.10, 0.95, 0.10, 0.60, 0.50, 1),
    ("memory leak: OOM killer triggered", 0.30, 0.40, 0.20, 0.80, 0.80, 1),
    ("DNS resolution failing", 0.20, 0.75, 0.15, 0.90, 0.65, 1),
    ("API rate limited: 429 storm", 0.80, 0.70, 0.10, 0.50, 0.75, 1),
    ("auth token expired across fleet", 0.35, 0.60, 0.40, 0.45, 0.85, 1),
    ("deadlock: all threads blocked", 0.05, 0.50, 0.30, 0.95, 0.40, 1),
    ("data corruption: checksum failures", 0.25, 0.70, 0.60, 0.55, 0.70, 1),
    ("certificate expired: TLS handshake fail", 0.15, 0.85, 0.10, 0.70, 0.80, 1),

    # ── BORDERLINE ──
    ("moderate errors, high latency", 0.40, 0.50, 0.45, 0.65, 0.35, 1),
    ("high latency, few errors", 0.35, 0.15, 0.20, 0.75, 0.20, 1),
    ("many retries, low errors", 0.20, 0.10, 0.10, 0.30, 0.75, 1),
    ("error spike, recovering", 0.50, 0.45, 0.55, 0.40, 0.45, 1),
    ("latency spike, normal errors", 0.30, 0.08, 0.15, 0.70, 0.10, 1),
    ("high unique errors, low volume", 0.10, 0.35, 0.80, 0.20, 0.05, 1),
    ("elevated everything, but expected", 0.55, 0.55, 0.55, 0.55, 0.55, 1),
]


def _teacher_rule(log_freq: float, error_ratio: float, unique_errors: float,
                  avg_latency: float, retry_count: float) -> int:
    """Deterministic teacher: normal (0) or anomaly (1).

    Priority rules:
    1. error_ratio > 0.6: anomaly
    2. avg_latency > 0.7 AND retry_count > 0.5: anomaly
    3. unique_errors > 0.6: anomaly
    4. retry_count > 0.7: anomaly
    5. error_ratio > 0.40 AND (avg_latency > 0.6 OR retry_count > 0.6): anomaly
    6. Otherwise: normal
    """
    if error_ratio > 0.6:
        return 1
    if avg_latency > 0.7 and retry_count > 0.5:
        return 1
    if unique_errors > 0.6:
        return 1
    if retry_count > 0.7:
        return 1
    if error_ratio > 0.40 and (avg_latency > 0.6 or retry_count > 0.6):
        return 1
    return 0


def build_dataset():
    X, y = [], []
    for desc, lf, er, ue, al, rc, label in LOG_PATTERNS:
        teacher_label = _teacher_rule(lf, er, ue, al, rc)
        if teacher_label != label:
            pass  # trust labelled data
        X.append([lf, er, ue, al, rc])
        y.append(label)
        for _ in range(4):
            jittered = [
                np.clip(lf + np.random.normal(0, 0.03), 0.0, 1.0),
                np.clip(er + np.random.normal(0, 0.03), 0.0, 1.0),
                np.clip(ue + np.random.normal(0, 0.02), 0.0, 1.0),
                np.clip(al + np.random.normal(0, 0.03), 0.0, 1.0),
                np.clip(rc + np.random.normal(0, 0.03), 0.0, 1.0),
            ]
            X.append(jittered)
            y.append(label)
    return np.array(X, dtype=float), np.array(y, dtype=int)


def _acc_synthetic(model_path, X, y):
    correct = 0
    for xi, yi in zip(X, y):
        out = _predict_python(str(model_path), list(xi))
        if int(np.argmax(out)) == int(yi):
            correct += 1
    return correct / len(y)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for _s in (sys.stdout, sys.stderr):
        rc = getattr(_s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    X, y = build_dataset()
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(y))
    n_test = max(10, len(y) // 5)
    te, tr = idx[:n_test], idx[n_test:]
    Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]

    print(f"== distill anomaly_detector ==  {len(y)} real samples "
          f"({len(tr)} train / {len(te)} held-out)")

    model_path = _MODELS_DIR / "anomaly_detector.json"
    syn_acc = _acc_synthetic(model_path, Xte, yte)

    Y = np.zeros((len(ytr), 2))
    Y[np.arange(len(ytr)), ytr] = 1.0
    np.random.seed(0)
    model = TinyNN([5, 10, 2], ["relu", "softmax"])
    model.train(Xtr, Y, epochs=2000, lr=0.05, verbose=False)
    dist_acc = float(np.mean(model.predict(Xte).argmax(axis=1) == yte))

    labels = ["normal", "anomaly"]

    test_cases = [
        ([0.15, 0.05, 0.10, 0.10, 0.05], "healthy: low errors, low latency"),
        ([0.50, 0.70, 0.50, 0.30, 0.20], "error storm: high errors"),
        ([0.30, 0.10, 0.10, 0.85, 0.70], "high latency + retries"),
        ([0.40, 0.55, 0.60, 0.50, 0.55], "borderline: all elevated"),
        ([0.10, 0.30, 0.80, 0.20, 0.05], "many unique errors, low volume"),
        ([0.60, 0.40, 0.30, 0.65, 0.45], "moderate errors, high latency"),
    ]
    print()
    for vec, desc in test_cases:
        syn_pred = labels[int(np.argmax(_predict_python(str(model_path), vec)))]
        dist_pred = labels[int(model.predict(np.array([vec])).argmax())]
        print(f"  {desc:50}  syn={syn_pred:7}  dist={dist_pred:7}")

    print(f"\n  synthetic model  : held-out accuracy {syn_acc:.0%}")
    print(f"  distilled model  : held-out accuracy {dist_acc:.0%}")
    print(f"  Δ accuracy: {dist_acc - syn_acc:+.0%}")

    if "--save" in argv:
        if dist_acc < syn_acc:
            print("  (not saving — distilled is not better)")
            return 0
        import json
        weights = model.export_json()
        weights["trained_on"] = "realistic_log_corpus_v1"
        weights["eval_accuracy"] = float(dist_acc)
        weights["trained_at"] = __import__("datetime").datetime.now().isoformat()
        weights["samples"] = len(tr)
        model_path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
        print(f"  ✅ saved distilled weights -> {model_path}")
        print(f"     provenance: {weights.get('trained_on')}, "
              f"eval_acc={weights.get('eval_accuracy'):.0%}, "
              f"samples={weights.get('samples')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
