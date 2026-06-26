#!/usr/bin/env python3
"""Tests for botte_nn — CLI + Python inference.

    python -m skills.botte_nn.test_botte_nn
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()  # Windows cp1252 consoles crash on the ✅/→ output below.

from skills.botte_nn.cli import (
    _find_model, _predict_python, _MODEL_META, _MODELS_DIR,
    do_predict, do_list, do_which,
)


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


class FakeArgs:
    """Minimal argparse namespace for testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def main() -> int:
    state = [0, 0]
    print("== botte_nn tests ==")

    # ── Model discovery ──
    for name in ["effort_classifier", "binary_router", "anomaly_detector"]:
        meta = _find_model(name)
        _ok(f"_find_model('{name}') finds model",
            meta is not None and meta["path"].endswith(".json"), state)
        _ok(f"model '{name}' JSON file exists",
            Path(meta["path"]).exists() if meta else False, state)

    # ── Model metadata ──
    _ok("effort_classifier has 4 inputs", _MODEL_META["effort_classifier"]["input_size"] == 4, state)
    _ok("effort_classifier has 3 outputs", _MODEL_META["effort_classifier"]["output_size"] == 3, state)
    _ok("binary_router has 3 inputs", _MODEL_META["binary_router"]["input_size"] == 3, state)
    _ok("anomaly_detector has 5 inputs", _MODEL_META["anomaly_detector"]["input_size"] == 5, state)

    # ── Python inference ──
    for name, meta in _MODEL_META.items():
        p = _MODELS_DIR / meta["path"]
        if not p.exists():
            continue
        fake_input = [0.5] * meta["input_size"]
        try:
            output = _predict_python(str(p), fake_input)
            _ok(f"{name}: predict returns {meta['output_size']} outputs",
                len(output) == meta["output_size"], state)
            _ok(f"{name}: all outputs are floats",
                all(isinstance(v, float) for v in output), state)
            _ok(f"{name}: softmax sums to ~1.0 (if applicable)",
                abs(sum(output) - 1.0) < 0.01, state)
        except Exception as e:
            _ok(f"{name}: predict throws '{e}'", False, state)

    # ── Edge cases ──
    _ok("_find_model on nonexistent name returns None",
        _find_model("nonexistent_model") is None, state)

    # ── Effort classifier runs without error ──
    p = _MODELS_DIR / "effort_classifier.json"
    if p.exists():
        easy = _predict_python(str(p), [0.1, 0.1, 0.0, 0.1])
        _ok("effort classifier runs and returns 3 values",
            len(easy) == 3, state)

    # ── Binary router semantics ──
    p = _MODELS_DIR / "binary_router.json"
    if p.exists():
        local_task = _predict_python(str(p), [0.2, 0.9, 1.0])
        cloud_task = _predict_python(str(p), [0.9, 0.1, 0.0])
        _ok("simple + budget + local → local class (index 0)",
            local_task.index(max(local_task)) == 0, state)

    # ── do_list ──
    try:
        do_list(FakeArgs())
        _ok("do_list() runs without error", True, state)
    except Exception as e:
        _ok(f"do_list() throws '{e}'", False, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
