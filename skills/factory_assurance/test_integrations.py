#!/usr/bin/env python3
"""Integration-contract tests for Factory Assurance adapters and controls."""

from __future__ import annotations

import json
from copy import deepcopy
import tempfile
from pathlib import Path

from skills.capabilities.effects import contract_template
from skills.capabilities.observations import digest, empty_report, validate_report

from .adapters import effect_manifest_to_assurance, holdout_attestation, observation_to_effects
from .assurance import evaluate_assurance
from .control_bridge import control_loop_signal
from .mutations import MUTATION_OPERATORS, mutate_assurance_record
from .test_factory_assurance import _fixture


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def _observation(manifest: dict) -> dict:
    """Build a full, valid transport fixture without executing a network call."""
    report = empty_report("a" * 32)
    report["process"] = {"status": "exited", "exit_code": 0}
    declaration_ref = digest(manifest)
    report["declarations"] = {declaration_ref: manifest}
    report["calls"] = [{"id": "c1", "parent_id": None, "capability_id": manifest["capability_id"],
                        "operation": "synthetic", "source_path": "synthetic.py", "context": {},
                        "status": "returned", "duration_ms": 0, "declaration_status": "declared",
                        "declaration_ref": declaration_ref}]
    report["observations"] = [{
        "id": "o1", "call_id": "c1", "resource": "synthetic.json",
        "effect_ref": "/expected_effects/0", "facet": "file_present_after_write",
        "write_status": "returned", "comparison": "supported",
        "before": {"state": "missing", "sha256": None, "size": None},
        "after": {"state": "present", "sha256": "b" * 64, "size": 1},
    }]
    target = {"id": "t1", "scheme": "https", "address_kind": "hostname"}
    report["network"] = [{
        "id": "n1", "call_id": "c1", "transport": "http", "method": "GET", "target": target,
        "effect_ref": "/downstream_effects/0", "facet": "transport_response", "status": "returned",
        "http_status": 200, "response_target": target, "origin_changed": False, "response_complete": True,
        "duration_ms": 0, "error_kind": None, "comparison": "supported", "remote_effects": "unknown",
    }]
    assert validate_report(report) == [], validate_report(report)
    return report


def main() -> int:
    state = [0, 0]
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "SKILL.md").write_text("Public synthetic integration fixture.\n", encoding="utf-8")
        manifest = contract_template(root, "example:skills/demo")
        manifest["expected_effects"][0]["effect"] = "writes one file"
        manifest["downstream_effects"] = [deepcopy(manifest["expected_effects"][0])]
        manifest["downstream_effects"][0]["effect"] = "consumer reloads it"
        mp = root / "effects.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        adapted = effect_manifest_to_assurance(mp)
        expected_ref = f"sha256:{digest(manifest)}#/expected_effects/0"
        downstream_ref = f"sha256:{digest(manifest)}#/downstream_effects/0"
        _ok("PR108 effect manifest adapts deterministically",
            adapted["declared"] == [expected_ref, downstream_ref], state)
        _ok("effect adapter emits stable digest", len(adapted["declaration_digest"]) == 64, state)

        observation = _observation(manifest)
        op = root / "obs.json"
        op.write_text(json.dumps(observation), encoding="utf-8")
        observed = observation_to_effects(op)
        _ok("observed refs are retained", observed["observed"] == [downstream_ref, expected_ref], state)
        _ok("unknown remote effects remain unresolved", downstream_ref in observed["unresolved"], state)

        observation["schema"] = "botte.effect-observations/v1"
        del observation["network"]
        op.write_text(json.dumps(observation), encoding="utf-8")
        _ok("valid v1 file evidence remains supported", observation_to_effects(op) == {
            "observed": [expected_ref], "unresolved": [],
        }, state)
        matching = _fixture()
        matching["effects"] = {"declared": adapted["declared"], **observation_to_effects(op)}
        _ok("same declaration digest remains review-ready",
            evaluate_assurance(matching)["status"] == "review_ready", state)
        for status in ("raised", "running"):
            interrupted = deepcopy(observation)
            interrupted["calls"][0]["status"] = status
            op.write_text(json.dumps(interrupted), encoding="utf-8")
            _ok(f"{status} call remains unresolved", bool(observation_to_effects(op)["unresolved"]), state)

    attestation = holdout_attestation(
        set_id="private-v1", digest="a" * 64, candidate_sha="b" * 40,
        passed=True, case_count=12,
    )
    _ok("holdout attestation excludes secret cases", attestation["contains_cases"] is False, state)
    _ok("holdout attestation binds candidate", attestation["candidate_sha"] == "b" * 40, state)

    for operator in MUTATION_OPERATORS:
        mutated = mutate_assurance_record(_fixture(), operator)
        decision = evaluate_assurance(mutated)
        _ok(f"mutation {operator} is caught", decision["status"] == "hold", state)

    signal = control_loop_signal(evaluate_assurance(_fixture()))
    _ok("control bridge records success without policy apply", signal["success"] and signal["apply_policy_change"] is False, state)
    _ok("control bridge cannot merge or deploy", not signal["may_merge_automatically"] and not signal["may_deploy_automatically"], state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
