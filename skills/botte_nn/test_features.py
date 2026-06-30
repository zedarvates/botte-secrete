#!/usr/bin/env python3
"""Tests for botte_nn.features — schema integrity, validation, extractors, classify.

    python skills/botte_nn/test_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.botte_nn import features
from skills.botte_nn.cli import _MODEL_META


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== botte_nn.features tests ==")

    # 1. Every schema's length matches the model's declared input_size — the guard
    #    against schema drift after a retrain.
    for model, meta in _MODEL_META.items():
        _ok(f"{model}: schema has {meta['input_size']} features",
            len(features.SCHEMAS.get(model, [])) == meta["input_size"], state)

    # 2. featurize validates names and clamps ranges.
    vec = features.featurize("binary_router",
                             {"complexity": 1.5, "budget_ratio": -0.2, "has_local_model": 1})
    _ok("featurize clamps to [lo,hi]", vec == [1.0, 0.0, 1.0], state)

    for bad, why in [({"complexity": 0.1}, "missing"),
                     ({"complexity": 0.1, "budget_ratio": 0.1,
                       "has_local_model": 1, "bogus": 1}, "extra")]:
        try:
            features.featurize("binary_router", bad)
            _ok(f"featurize rejects {why} feature", False, state)
        except ValueError:
            _ok(f"featurize rejects {why} feature", True, state)

    try:
        features.featurize("nope", {})
        _ok("featurize rejects unknown model", False, state)
    except ValueError:
        _ok("featurize rejects unknown model", True, state)

    # 3. Error extractor reads a real Python traceback deterministically.
    tb = ("Traceback (most recent call last):\n"
          '  File "app.py", line 10, in <module>\n'
          "ValueError: invalid literal for int() with base 10: 'x'\n")
    ev = features.error_classifier_values(tb, exit_code=1)
    _ok("error extractor: has_traceback=1", ev["has_traceback"] == 1.0, state)
    _ok("error extractor: kw_runtime=1 (ValueError)", ev["kw_runtime"] == 1.0, state)
    _ok("error extractor: exit_code_nonzero=1", ev["exit_code_nonzero"] == 1.0, state)
    _ok("error extractor produces a full valid vector",
        len(features.featurize("error_classifier", ev)) == 12, state)

    # 4. Code extractor detects code.
    cv = features.effort_classifier_values("def f(x):\n    return x + 1\n")
    _ok("effort extractor: is_code=1 for code", cv["is_code"] == 1.0, state)
    _ok("effort extractor: is_code=0 for prose",
        features.effort_classifier_values("please summarize this article")["is_code"] == 0.0,
        state)

    # 5. classify(): named features → label, in one call.
    label, conf, probs = features.classify(
        "binary_router", features.binary_router_values(0.2, 1.0, has_local=True))
    _ok(f"classify(binary_router, easy+local) → 'local' ({conf:.2f})",
        label == "local" and 0.0 <= conf <= 1.0 and len(probs) == 2, state)

    # Regression guard for the distilled error_classifier: a ValueError traceback
    # must classify as 'runtime' (the synthetic model wrongly said 'syntax').
    elabel, econf, _ = features.classify("error_classifier", ev)
    _ok(f"classify(error_classifier, ValueError tb) → 'runtime' (distilled) [{elabel}]",
        elabel == "runtime", state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
