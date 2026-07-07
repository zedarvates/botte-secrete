#!/usr/bin/env python3
"""Distill binary_router from realistic task patterns instead of np.random noise.

The shipped binary_router is trained on uniform random noise + a 3-line rule:
    should_cloud = complexity > 0.6 AND (no_local OR budget_exhausted)
with 10% noise flipped. It encodes an invented rule, not reality.

This script creates a corpus of realistic task descriptions, maps each to its
expected routing decision via a deterministic teacher heuristic, then re-trains
the micro-NN on these real (features -> label) pairs.

    python -m skills.botte_nn.training.distill_binary_router          # report only
    python -m skills.botte_nn.training.distill_binary_router --save   # write weights
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from skills.botte_nn import features
from skills.botte_nn.cli import _predict_python, _MODELS_DIR
from skills.botte_nn.training.train import TinyNN


# Realistic task descriptions -> (complexity, budget_ratio, has_local_model, label)
# label: 0 = local, 1 = cloud
# Each tuple: (description, complexity, budget_ratio, has_local, cloud?)
REAL_TASKS: list[tuple[str, float, float, float, int]] = [
    # ── LOCAL tasks (cheap, mechanical, classification) ──
    ("rename variable in 3 files", 0.15, 0.95, 0.0, 0),
    ("format code with ruff", 0.10, 0.90, 0.0, 0),
    ("add type hints to function", 0.20, 0.85, 0.0, 0),
    ("sort imports alphabetically", 0.05, 0.92, 0.0, 0),
    ("extract repeated string into constant", 0.12, 0.88, 0.0, 0),
    ("add docstring to public function", 0.15, 0.87, 0.0, 0),
    ("replace deprecated API call", 0.22, 0.83, 0.0, 0),
    ("fix lint warnings (15 files)", 0.30, 0.80, 0.0, 0),
    ("classify error from stack trace", 0.25, 0.82, 0.0, 0),
    ("summarise 2-page document", 0.18, 0.78, 0.0, 0),
    ("extract email addresses from log", 0.12, 0.91, 0.0, 0),
    ("translate 5 error messages to French", 0.20, 0.75, 0.0, 0),
    ("check JSON syntax of config file", 0.08, 0.93, 0.0, 0),
    ("find all TODO comments in repo", 0.10, 0.89, 0.0, 0),
    ("generate git commit message from diff", 0.25, 0.85, 0.0, 0),

    # ── LOCAL with model ──
    ("format Python code with black", 0.10, 0.95, 1.0, 0),
    ("find unused imports", 0.15, 0.90, 1.0, 0),
    ("simple regex extraction", 0.12, 0.88, 1.0, 0),
    ("check for common security patterns", 0.30, 0.85, 1.0, 0),

    # ── CLOUD tasks (complex reasoning, multi-file, architecture) ──
    ("debug race condition in async code", 0.75, 0.70, 0.0, 1),
    ("audit security across 50+ files", 0.85, 0.65, 0.0, 1),
    ("refactor authentication middleware", 0.80, 0.72, 0.0, 1),
    ("design database schema for new feature", 0.70, 0.68, 0.0, 1),
    ("write integration tests for payment flow", 0.65, 0.60, 0.0, 1),
    ("fix memory leak in C extension", 0.90, 0.55, 0.0, 1),
    ("rewrite pipeline from sync to async", 0.78, 0.62, 0.0, 1),
    ("implement OAuth2 flow from scratch", 0.72, 0.58, 0.0, 1),
    ("analyze crash dump from production", 0.88, 0.50, 0.0, 1),
    ("migrate from SQLite to PostgreSQL", 0.75, 0.55, 0.0, 1),
    ("optimize N+1 query problem in ORM", 0.68, 0.65, 0.0, 1),
    ("design rate-limiting strategy", 0.62, 0.70, 0.0, 1),
    ("audit compliance with GDPR requirements", 0.80, 0.45, 0.0, 1),
    ("investigate root cause of intermittent 500", 0.85, 0.40, 0.0, 1),
    ("rewrite data ingestion pipeline", 0.72, 0.52, 0.0, 1),

    # ── CLOUD with local model available (still complex enough) ──
    ("implement distributed lock with Redis", 0.75, 0.78, 1.0, 1),
    ("design circuit breaker for microservices", 0.80, 0.72, 1.0, 1),
    ("write data migration script with rollback", 0.70, 0.68, 1.0, 1),
    ("audit thread safety of shared cache", 0.82, 0.60, 1.0, 1),
    ("design API versioning strategy", 0.68, 0.75, 1.0, 1),

    # ── CLOUD: budget exhausted forces cloud escalation ──
    ("fix typo in README", 0.05, 0.15, 0.0, 1),   # trivial but no budget
    ("rename variable", 0.10, 0.10, 0.0, 1),
    ("add comment to function", 0.08, 0.20, 1.0, 1),  # local model exists but no budget

    # ── Edge cases: borderline decisions ──
    ("fix 3 moderate bugs with tests", 0.55, 0.75, 0.0, 0),  # medium, enough budget -> local
    ("refactor 2 related modules", 0.58, 0.55, 0.0, 1),      # borderline -> cloud (low budget)
    ("add feature flag with rollout", 0.52, 0.80, 1.0, 0),    # medium, local model -> local
    ("write complex regex with lookahead", 0.45, 0.85, 0.0, 0),  # not complex enough
    ("debug deadlock in thread pool", 0.72, 0.68, 0.0, 1),    # complex, borderline budget
    ("implement custom serializer", 0.58, 0.45, 0.0, 1),      # medium but low budget -> cloud
    ("fix flaky integration test", 0.60, 0.55, 0.0, 1),       # borderline complex, low budget
    ("add logging to 20 endpoints", 0.35, 0.24, 0.0, 1),      # simple but NO budget
]


def _teacher_rule(complexity: float, budget_ratio: float, has_local: float) -> int:
    """Deterministic teacher: decides local (0) or cloud (1) from features.

    Rules (in priority order):
    1. Budget exhausted (< 0.25): always cloud
    2. Complexity > 0.65: cloud (needs reasoning)
    3. Complexity > 0.55 AND (no_local OR budget < 0.3): cloud
    4. Otherwise: local
    """
    if budget_ratio < 0.25:
        return 1
    if complexity > 0.65:
        return 1
    if complexity > 0.55 and (has_local < 0.5 or budget_ratio < 0.30):
        return 1
    return 0


def build_dataset():
    """Build (features, labels) from the realistic task corpus."""
    X, y = [], []
    for desc, cpx, budget, has_local, label in REAL_TASKS:
        # Verify teacher agrees with the labelled outcome
        teacher_label = _teacher_rule(cpx, budget, has_local)
        if teacher_label != label:
            print(f"  ⚠️  Teacher disagrees on: {desc} (teacher={teacher_label}, corpus={label})")
        # Add base sample
        X.append([cpx, budget, has_local])
        y.append(label)
        # Add jittered variants (±5% noise) to increase dataset size
        for _ in range(4):
            jittered = [
                np.clip(cpx + np.random.normal(0, 0.03), 0.0, 1.0),
                np.clip(budget + np.random.normal(0, 0.03), 0.0, 1.0),
                has_local if np.random.random() > 0.02 else (1.0 - has_local),
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

    print(f"== distill binary_router ==  {len(y)} real samples "
          f"({len(tr)} train / {len(te)} held-out)")

    model_path = _MODELS_DIR / "binary_router.json"
    syn_acc = _acc_synthetic(model_path, Xte, yte)

    Y = np.zeros((len(ytr), 2))
    Y[np.arange(len(ytr)), ytr] = 1.0
    np.random.seed(0)
    model = TinyNN([3, 8, 2], ["relu", "softmax"])
    model.train(Xtr, Y, epochs=2000, lr=0.05, verbose=False)
    dist_acc = float(np.mean(model.predict(Xte).argmax(axis=1) == yte))

    labels = ["local", "cloud"]

    # Check a few borderline cases
    test_cases = [
        ([0.55, 0.30, 0.0], "borderline: medium complexity, low budget, no local"),
        ([0.30, 0.95, 1.0], "clear local: simple, budget OK, has local"),
        ([0.80, 0.70, 0.0], "clear cloud: complex, no local"),
        ([0.10, 0.10, 0.0], "budget exhausted: trivial but must cloud"),
        ([0.50, 0.80, 0.0], "medium, budget OK, no local"),
    ]
    print()
    for vec, desc in test_cases:
        syn_pred = labels[int(np.argmax(_predict_python(str(model_path), vec)))]
        dist_pred = labels[int(model.predict(np.array([vec])).argmax())]
        print(f"  {desc:55}  syn={syn_pred:5}  dist={dist_pred:5}")

    print(f"\n  synthetic model  : held-out accuracy {syn_acc:.0%}")
    print(f"  distilled model  : held-out accuracy {dist_acc:.0%}")
    print(f"  Δ accuracy: {dist_acc - syn_acc:+.0%}")

    if "--save" in argv:
        if dist_acc < syn_acc:
            print("  (not saving — distilled is not better)")
            return 0
        import json
        # Add provenance
        weights = model.export_json()
        weights["trained_on"] = "realistic_task_corpus_v1"
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
