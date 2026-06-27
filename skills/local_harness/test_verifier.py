#!/usr/bin/env python3
"""Tests for local_harness.verifier — the deterministic anti-hallucination checks.

    python -m skills.local_harness.test_verifier
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.local_harness import verifier as V


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== local_harness.verifier tests ==")

    # ── schema_ok ──
    schema = {"required": ["answer"], "properties": {
        "answer": {"type": "string", "enum": ["local", "cloud"]},
        "conf": {"type": "number", "minimum": 0, "maximum": 1}}}
    _ok("schema_ok: valid object passes",
        V.schema_ok({"answer": "local", "conf": 0.9}, schema).ok, state)
    _ok("schema_ok: missing required fails",
        not V.schema_ok({"conf": 0.5}, schema).ok, state)
    _ok("schema_ok: wrong type fails",
        not V.schema_ok({"answer": 123}, schema).ok, state)
    _ok("schema_ok: enum violation fails",
        not V.schema_ok({"answer": "moon"}, schema).ok, state)
    _ok("schema_ok: out-of-range fails",
        not V.schema_ok({"answer": "local", "conf": 1.5}, schema).ok, state)
    _ok("schema_ok: non-dict fails", not V.schema_ok("nope", schema).ok, state)

    # ── evidence_in_context ──
    ctx = "The retry budget is 3 attempts and the timeout is 30 seconds."
    _ok("evidence_in_context: grounded span passes",
        V.evidence_in_context(["retry budget is 3"], ctx).ok, state)
    _ok("evidence_in_context: case/space tolerant",
        V.evidence_in_context(["RETRY   budget IS 3"], ctx).ok, state)
    _ok("evidence_in_context: fabricated span fails",
        not V.evidence_in_context(["the timeout is 5 minutes"], ctx).ok, state)

    # ── citations_exist ──
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
        _ok("citations_exist: existing file passes",
            V.citations_exist(["mod.py"], d).ok, state)
        _ok("citations_exist: file:symbol that exists passes",
            V.citations_exist(["mod.py:foo"], d).ok, state)
        _ok("citations_exist: file:lineno passes (numeric)",
            V.citations_exist(["mod.py:2"], d).ok, state)
        _ok("citations_exist: missing symbol fails",
            not V.citations_exist(["mod.py:bar"], d).ok, state)
        _ok("citations_exist: missing file fails",
            not V.citations_exist(["ghost.py"], d).ok, state)

    # ── code_parses ──
    _ok("code_parses: valid python passes",
        V.code_parses("def f(x):\n    return x + 1\n").ok, state)
    _ok("code_parses: syntax error fails",
        not V.code_parses("def f(x):\n    return x +\n").ok, state)
    _ok("code_parses: empty fails", not V.code_parses("").ok, state)
    _ok("code_parses: balanced non-python passes",
        V.code_parses("function f(){ return 1; }", lang="js").ok, state)
    _ok("code_parses: unbalanced non-python fails",
        not V.code_parses("function f(){ return 1;", lang="js").ok, state)

    # ── verify orchestrator ──
    good = {"answer": "local", "evidence": ["retry budget is 3"]}
    r = V.verify(good, ["schema", "evidence_in_context"], context=ctx, schema=schema)
    _ok("verify: all checks pass → ok", r.ok and r.checks["schema"].ok, state)

    bad = {"answer": "local", "evidence": ["a fact not present anywhere"]}
    r2 = V.verify(bad, ["schema", "evidence_in_context"], context=ctx, schema=schema)
    _ok("verify: one failing check → not ok", not r2.ok, state)
    _ok("verify: unknown check → not ok",
        not V.verify({}, ["bogus"]).ok, state)
    _ok("verify: to_dict is serializable",
        r2.to_dict()["checks"]["evidence_in_context"]["ok"] is False, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
