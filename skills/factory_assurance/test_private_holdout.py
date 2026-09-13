#!/usr/bin/env python3
"""Deterministic tests for the private/external holdout runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .private_holdout import PrivateHoldoutError, load_private_set, run_private_holdout


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def _write(root: Path, payload: dict) -> Path:
    path = root / "private.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def main() -> int:
    state = [0, 0]
    sha = "a" * 40
    secret = "PRIVATE-STORYCORE-CASE-PAYLOAD"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _write(root, {
            "set_id": "storycore-private-v1",
            "cases": [
                {"id": "h-001", "input": {"secret": secret, "expected": True}},
                {"id": "h-002", "input": {"secret": "ANOTHER-PRIVATE-CASE", "expected": True}},
            ],
        })
        attestation = run_private_holdout(
            private_set_path=path,
            candidate_sha=sha,
            evaluator=lambda case: bool(case["input"]["expected"]),
        )
        rendered = json.dumps(attestation, sort_keys=True)
        _ok("passing private set emits pass attestation", attestation["status"] == "pass", state)
        _ok("attestation records case count", attestation["case_count"] == 2, state)
        _ok("attestation explicitly contains no cases", attestation["contains_cases"] is False, state)
        _ok("private payload is absent from public attestation", secret not in rendered and "ANOTHER-PRIVATE-CASE" not in rendered, state)
        _ok("attestation binds exact candidate", attestation["candidate_sha"] == sha, state)
        _ok("private set digest is present", len(attestation["set_digest_sha256"]) == 64, state)

        failing = run_private_holdout(
            private_set_path=path,
            candidate_sha=sha,
            evaluator=lambda case: case["id"] != "h-002",
        )
        _ok("one failed private case fails whole attestation", failing["status"] == "fail", state)

        duplicate = _write(root, {
            "set_id": "bad",
            "cases": [{"id": "same", "input": 1}, {"id": "same", "input": 2}],
        })
        try:
            load_private_set(duplicate)
            duplicate_blocked = False
        except PrivateHoldoutError:
            duplicate_blocked = True
        _ok("duplicate private IDs fail closed", duplicate_blocked, state)

        valid = _write(root, {"set_id": "valid", "cases": [{"id": "x", "input": 1}]})
        try:
            run_private_holdout(private_set_path=valid, candidate_sha=sha)
            missing_eval_blocked = False
        except PrivateHoldoutError:
            missing_eval_blocked = True
        _ok("missing evaluator fails closed", missing_eval_blocked, state)

        try:
            run_private_holdout(
                private_set_path=valid,
                candidate_sha=sha,
                evaluator=lambda case: True,
                evaluator_argv=["python"],
            )
            dual_eval_blocked = False
        except PrivateHoldoutError:
            dual_eval_blocked = True
        _ok("ambiguous dual evaluator configuration fails closed", dual_eval_blocked, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
