#!/usr/bin/env python3
"""Deterministic tests for the Factory Assurance Layer."""

from __future__ import annotations

from .assurance import evaluate_assurance


def _fixture() -> dict:
    sha = "a" * 40
    return {
        "schema_version": 1,
        "action_id": "pilot-001",
        "stage": "gated",
        "requested_autonomy": "gated",
        "mission": {
            "goals": ["fix one bounded non-critical defect"],
            "invariants": ["no unrelated behavior changes"],
            "non_goals": ["architecture rewrite"],
            "forbidden_transformations": ["disable tests"],
            "within_mission": True,
        },
        "actors": {"builder": "builder-a", "judge": "judge-b"},
        "effects": {
            "declared": ["source"],
            "observed": ["source"],
            "unresolved": [],
        },
        "evidence": [
            {"name": "unit", "status": "pass", "required": True},
            {"name": "runtime", "status": "pass", "required": True},
        ],
        "controls": {
            "positive_control": "pass",
            "negative_control": "fail",
            "holdout_scope": "private_external",
            "historical_regressions_checked": True,
            "adversarial_cases_checked": True,
        },
        "identity": {
            "source_sha": sha,
            "build_sha": sha,
            "tested_sha": sha,
            "deployed_sha": None,
        },
    }


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]

    good = evaluate_assurance(_fixture())
    _ok("complete record becomes review-ready", good["status"] == "review_ready", state)
    _ok("review-ready never means auto-merge", good["may_merge_automatically"] is False, state)
    _ok("review-ready never means auto-deploy", good["may_deploy_automatically"] is False, state)

    same_actor = _fixture()
    same_actor["actors"]["judge"] = same_actor["actors"]["builder"]
    result = evaluate_assurance(same_actor)
    _ok("self-judging builder is blocked", result["status"] == "hold", state)

    drift = _fixture()
    drift["effects"]["observed"].append("workflow")
    result = evaluate_assurance(drift)
    _ok("undeclared effect is blocked", any("unexpected effects" in b for b in result["blockers"]), state)

    bad_mutation = _fixture()
    bad_mutation["controls"]["negative_control"] = "pass"
    result = evaluate_assurance(bad_mutation)
    _ok("gate must prove it can fail", any("negative/mutation" in b for b in result["blockers"]), state)

    visible_holdout = _fixture()
    visible_holdout["controls"]["holdout_scope"] = "repository"
    result = evaluate_assurance(visible_holdout)
    _ok("builder-visible holdout is blocked", any("holdout" in b for b in result["blockers"]), state)

    identity_drift = _fixture()
    identity_drift["identity"]["tested_sha"] = "b" * 40
    result = evaluate_assurance(identity_drift)
    _ok("exact-head mismatch is blocked", any("identity mismatch" in b for b in result["blockers"]), state)

    failed_evidence = _fixture()
    failed_evidence["evidence"][0]["status"] = "fail"
    result = evaluate_assurance(failed_evidence)
    _ok("required failed evidence is blocked", any("required evidence" in b for b in result["blockers"]), state)

    excessive = _fixture()
    excessive["requested_autonomy"] = "autonomous"
    result = evaluate_assurance(excessive)
    _ok("unbounded autonomy is rejected", any("autonomy" in b for b in result["blockers"]), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
