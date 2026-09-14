#!/usr/bin/env python3
"""Integration-contract tests for Factory Assurance adapters and controls."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .adapters import effect_manifest_to_assurance, holdout_attestation, observation_to_effects
from .assurance import evaluate_assurance
from .control_bridge import control_loop_signal
from .mutations import MUTATION_OPERATORS, mutate_assurance_record
from .test_factory_assurance import _fixture


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        manifest = {
            "schema": "botte.capability-effects/v1",
            "capability_id": "example:skills/demo",
            "contract_version": "0.1.0",
            "preconditions": ["bounded task"],
            "expected_effects": [{"effect": "writes one file"}],
            "downstream_effects": [{"effect": "consumer reloads it"}],
            "required_scope": "task-local write authority",
            "reversibility": {"status": "partial"},
            "retry": {"semantics": "conditional"},
        }
        mp = root / "effects.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        adapted = effect_manifest_to_assurance(mp)
        _ok("PR108 effect manifest adapts deterministically",
            adapted["declared"] == ["/expected_effects/0", "/downstream_effects/0"], state)
        _ok("effect adapter emits stable digest", len(adapted["declaration_digest"]) == 64, state)

        observation = {
            "schema": "botte.effect-observations/v2",
            "observations": [{"id": "o1", "effect_ref": "/expected_effects/0", "comparison": "supported"}],
            "network": [{"id": "n1", "effect_ref": "/downstream_effects/0", "comparison": "supported", "remote_effects": "unknown"}],
            "problems": [],
        }
        op = root / "obs.json"
        op.write_text(json.dumps(observation), encoding="utf-8")
        observed = observation_to_effects(op)
        _ok("observed refs are retained", observed["observed"] == ["/downstream_effects/0", "/expected_effects/0"], state)
        _ok("unknown remote effects remain unresolved", "/downstream_effects/0" in observed["unresolved"], state)

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
