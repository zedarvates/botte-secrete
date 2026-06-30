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
    """Builds a fake skills/ tree: botte_nn + a consumer module."""
    bn = root / "botte_nn"
    (bn / "models").mkdir(parents=True)
    (bn / "training").mkdir()
    # grounded model: provenance + distill trainer + test guard
    (bn / "models" / "good.json").write_text(json.dumps(
        {"weights": [], "activations": ["relu"],
         "trained_on": "real labelled corpus", "eval_accuracy": 0.94}), encoding="utf-8")
    (bn / "training" / "distill_good.py").write_text(
        "# distill good from real labelled errors corpus\nimport json\n", encoding="utf-8")
    # synthetic + WIRED model (a consumer references it)
    (bn / "models" / "wired_fake.json").write_text(json.dumps(
        {"weights": [], "activations": ["relu"]}), encoding="utf-8")
    (bn / "training" / "train_wired_fake.py").write_text(
        "import numpy as np\nX = np.random.rand(100, 4)\n", encoding="utf-8")
    # synthetic + ORPHAN model (nobody references it)
    (bn / "models" / "orphan_fake.json").write_text(json.dumps(
        {"weights": [], "activations": ["relu"]}), encoding="utf-8")
    (bn / "training" / "train_orphan_fake.py").write_text(
        "import numpy as np\nY = np.random.randint(0, 3, 100)\n", encoding="utf-8")
    (bn / "test_features.py").write_text(
        "assert classify('good', x) == 'runtime'\n", encoding="utf-8")
    # a production consumer that uses 'wired_fake' (not under botte_nn infra)
    (root / "router").mkdir()
    (root / "router" / "belt.py").write_text(
        "from botte_nn import classify\nlabel = classify('wired_fake', sig)\n", encoding="utf-8")


def main() -> int:
    state = [0, 0]
    print("== nn_audit tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _fixture(root)
        r = audit_models(root / "botte_nn", scan_root=root)
        by = {m["model"]: m for m in r["models"]}

        _ok("audits all three models",
            set(by) == {"good", "wired_fake", "orphan_fake"}, state)
        _ok("real-data trainer → data_source 'real'", by["good"]["data_source"] == "real", state)
        _ok("np.random trainer → data_source 'synthetic'",
            by["wired_fake"]["data_source"] == "synthetic", state)
        _ok("provenance in json detected", by["good"]["has_provenance"], state)
        _ok("test guard detected for 'good'", by["good"]["has_test_guard"], state)
        _ok("grounded verdict for the real model", by["good"]["verdict"] == "grounded", state)

        # the wiring dimension
        _ok("consumer reference → wired", by["wired_fake"]["wired"] is True, state)
        _ok("no consumer → orphan", by["orphan_fake"]["wired"] is False, state)
        _ok("wired_fake lists its consumer", "belt.py" in by["wired_fake"]["usage"], state)
        _ok("synthetic + wired → 'drives behaviour' + at risk",
            "drives behaviour" in by["wired_fake"]["verdict"] and by["wired_fake"]["risk"], state)
        _ok("synthetic + orphan → 'delete or wire', not at risk",
            "orphan" in by["orphan_fake"]["verdict"] and by["orphan_fake"]["risk"] is False, state)

        _ok("summary counts are right",
            r["summary"]["grounded"] == 1 and r["summary"]["synthetic"] == 2
            and r["summary"]["orphan"] == 2 and r["summary"]["at_risk"] == 1, state)
        _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)

        # missing models dir → error, not crash
        with tempfile.TemporaryDirectory() as d2:
            _ok("missing models dir → error", "error" in audit_models(d2), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
