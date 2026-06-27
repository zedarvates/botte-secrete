#!/usr/bin/env python3
"""Tests for botte_nn.calibration — temperature scaling makes confidence meaningful.

    python -m skills.botte_nn.test_calibration
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.botte_nn import calibration as C


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== botte_nn.calibration tests ==")

    # ── apply_temperature ──
    _ok("T=1.0 is identity", C.apply_temperature([0.7, 0.3], 1.0) == [0.7, 0.3], state)
    soft = C.apply_temperature([0.9, 0.1], 2.0)
    _ok("T>1 softens (max prob drops)", max(soft) < 0.9, state)
    sharp = C.apply_temperature([0.7, 0.3], 0.5)
    _ok("T<1 sharpens (max prob rises)", max(sharp) > 0.7, state)
    _ok("stays a distribution (sums to 1)", abs(sum(soft) - 1.0) < 1e-9, state)

    # ── overconfident model: says 0.9 but is only 60% right ──
    probs = [[0.9, 0.1]] * 100
    labels = [0] * 60 + [1] * 40
    t = C.fit_temperature(probs, labels)
    _ok(f"fit_temperature softens an overconfident model (T={t} > 1)", t > 1.0, state)
    _ok("calibration reduces NLL",
        C.nll(probs, labels, t) < C.nll(probs, labels, 1.0), state)

    ece_before = C.expected_calibration_error(probs, labels)
    ece_after = C.expected_calibration_error([C.apply_temperature(p, t) for p in probs], labels)
    _ok(f"calibration reduces ECE ({ece_before} → {ece_after})", ece_after < ece_before, state)

    # ── a well-calibrated model needs ~no change ──
    good_probs = [[0.6, 0.4]] * 100
    good_labels = [0] * 60 + [1] * 40
    _ok("well-calibrated model has low ECE",
        C.expected_calibration_error(good_probs, good_labels) < 0.05, state)

    # ── persistence + cache (clean up the temp file) ──
    name = "_calib_test_tmp"
    path = C._calib_path(name)
    try:
        _ok("load defaults to 1.0 when uncalibrated", C.load_temperature(name) == 1.0, state)
        C._cache.pop(name, None)
        C.save_temperature(name, 2.5)
        _ok("save/load round-trip", C.load_temperature(name) == 2.5, state)
        rep = C.calibrate(name, probs, labels)
        _ok("calibrate() report: ece improves",
            rep["ece_after"] <= rep["ece_before"] and rep["samples"] == 100, state)
    finally:
        path.unlink(missing_ok=True)
        C._cache.pop(name, None)

    # ── the belt stays identity-safe when a model is uncalibrated ──
    from skills.auto_router import nn_belt
    C._cache.pop("binary_router", None)
    _ok("uncalibrated binary_router → T=1.0 (belt unchanged)",
        C.load_temperature("binary_router") == 1.0, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
