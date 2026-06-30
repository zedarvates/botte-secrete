#!/usr/bin/env python3
"""Tests for nn_audit — grounded vs synthetic micro-NN detection (hermetic).

    python -m skills.nn_audit.test_nn_audit
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.nn_audit import audit_models


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _fixture(root: Path) -> None:
    (root / "models").mkdir()
    (root / "training").mkdir()
    # grounded model: provenance in json + a distill trainer + a test guard
    (root / "models" / "good.json").write_text(json.dumps(
        {"weights": [], "activations": ["relu"],
         "trained_on": "real labelled corpus", "eval_accuracy": 0.94}), encoding="utf-8")
    (root / "training" / "distill_good.py").write_text(
        "# distill good from real labelled errors corpus\nimport json\n", encoding="utf-8")
    # synthetic model: np.random trainer, no provenance, no test guard
    (root / "models" / "fake.json").write_text(json.dumps(
        {"weights": [], "activations": ["relu"]}), encoding="utf-8")
    (root / "training" / "train_fake.py").write_text(
        "import numpy as np\nX = np.random.rand(100, 4)  # synthetic\n", encoding="utf-8")
    # a test that guards 'good' with an equality assertion
    (root / "test_features.py").write_text(
        "assert classify('good', x) == 'runtime'\n", encoding="utf-8")


def main() -> int:
    state = [0, 0]
    print("== nn_audit tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _fixture(root)
        r = audit_models(root)
        by = {m["model"]: m for m in r["models"]}

        _ok("audits both models", set(by) == {"good", "fake"}, state)
        _ok("real-data trainer → data_source 'real'", by["good"]["data_source"] == "real", state)
        _ok("np.random trainer → data_source 'synthetic'",
            by["fake"]["data_source"] == "synthetic", state)
        _ok("provenance in json detected", by["good"]["has_provenance"], state)
        _ok("missing provenance detected", not by["fake"]["has_provenance"], state)
        _ok("test guard detected for 'good'", by["good"]["has_test_guard"], state)
        _ok("no test guard for 'fake'", not by["fake"]["has_test_guard"], state)
        _ok("grounded verdict for the real model", by["good"]["verdict"] == "grounded", state)
        _ok("synthetic verdict flags rule-mimicry",
            "synthetic" in by["fake"]["verdict"], state)
        _ok("synthetic + no guard → at risk", by["fake"]["risk"] is True, state)
        _ok("summary counts are right",
            r["summary"]["grounded"] == 1 and r["summary"]["synthetic"] == 1
            and r["summary"]["grounded_pct"] == 50, state)
        _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)

        # missing models dir → error, not crash
        with tempfile.TemporaryDirectory() as d2:
            _ok("missing models dir → error", "error" in audit_models(d2), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
