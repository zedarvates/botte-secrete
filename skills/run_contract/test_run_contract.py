#!/usr/bin/env python3
"""Focused tests for mission, context-manifest and handoff contracts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.run_contract import (
    ContractError,
    build_handoff,
    compile_context_manifest,
    contract_fingerprint,
    validate_handoff,
    validate_mission,
)
from skills.run_contract.cli import main as cli_main


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _raises(callable_) -> bool:
    try:
        callable_()
    except ContractError:
        return True
    return False


def _mission(**overrides) -> dict:
    payload = {
        "schema": "botte.mission/v1",
        "mission_id": "pilot-contract-1",
        "objective": "Validate one bounded change without external publication.",
        "scope": {"include": ["skills/run_contract"], "exclude": ["private"]},
        "forbidden_actions": [
            "merge", "deploy", "release", "secrets", "payments", "publish"
        ],
        "authority": "SHADOW",
        "risk": "R2",
        "privacy": "PRIVATE",
        "capabilities": ["read", "test"],
        "budgets": {
            "max_iterations": 12,
            "max_tool_calls": 48,
            "max_wall_seconds": 900,
            "max_tokens": 10000,
            "max_cost_usd": 0,
            "max_revisions": 2,
        },
        "required_evidence": ["tests:run_contract"],
        "approval_gates": [],
        "rollback": {"required": False, "snapshot_ref": ""},
        "context": {
            "budget_tokens": 5000,
            "required_files": ["README.md"],
            "optional_files": ["ROADMAP.md"],
        },
    }
    payload.update(overrides)
    return payload


def _lease(worker_id: str = "worker-1", *, head_sha: str = "b" * 64) -> dict:
    return {
        "lease_id": "lease-1",
        "worker_id": worker_id,
        "state": "ACTIVE",
        "base_sha": "a" * 40,
        "head_sha": head_sha,
        "expires_at": "2026-09-02T00:00:00+00:00",
        "workspace_fingerprint": "c" * 64,
    }


def main() -> int:
    state = [0, 0]
    print("== run_contract tests ==")

    normalized = validate_mission(_mission())
    _ok("valid mission normalizes", normalized["authority"] == "SHADOW", state)
    _ok(
        "mission fingerprint is stable",
        contract_fingerprint(normalized) == contract_fingerprint(validate_mission(_mission())),
        state,
    )

    missing_owner_boundary = _mission()
    missing_owner_boundary["forbidden_actions"].remove("merge")
    _ok(
        "owner-only external actions fail closed",
        _raises(lambda: validate_mission(missing_owner_boundary)),
        state,
    )

    act = _mission(
        authority="ACT",
        rollback={"required": True, "snapshot_ref": "git:abc"},
    )
    _ok(
        "ACT without owner approval reference is rejected",
        _raises(lambda: validate_mission(act)),
        state,
    )
    act["owner_approval_ref"] = "owner:approval:opaque-17"
    _ok("ACT with approval and snapshot validates", bool(validate_mission(act)), state)

    high_risk = _mission(risk="R4")
    _ok(
        "R3/R4 require owner-review gate",
        _raises(lambda: validate_mission(high_risk)),
        state,
    )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".botte").mkdir()
        (root / ".botte" / "policy.md").write_text("never publish", encoding="utf-8")
        (root / "AGENTS.md").write_text("run tests", encoding="utf-8")
        (root / "README.md").write_text("readme", encoding="utf-8")
        (root / "ROADMAP.md").write_text("future " * 100, encoding="utf-8")
        manifest = compile_context_manifest(
            root, _mission(), generated_at="2026-09-01T00:00:00+00:00"
        )
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        _ok(
            "policy and directives are pinned and not compressible",
            not by_path[".botte/policy.md"]["compressible"]
            and not by_path["AGENTS.md"]["compressible"],
            state,
        )
        _ok("context manifest stores no raw content", not manifest["raw_content_stored"], state)
        _ok(
            "context manifest has self fingerprint",
            len(manifest["manifest_sha256"]) == 64,
            state,
        )

        tight = _mission()
        tight["context"]["budget_tokens"] = 2
        _ok(
            "required context cannot silently exceed budget",
            _raises(lambda: compile_context_manifest(root, tight)),
            state,
        )

        mission_path = root / "mission.json"
        mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
        _ok("CLI validates a mission", cli_main(["validate", str(mission_path)]) == 0, state)

    ready = build_handoff(
        _mission(),
        attempt_id="attempt-1",
        worker_id="worker-1",
        status="READY_FOR_REVIEW",
        workspace_lease=_lease(),
        checks=({"name": "tests", "status": "PASS", "evidence_ref": "test:1"},),
        evidence_refs=("test:1",),
        next_safe_action="Independent Gauntlet review.",
        created_at="2026-09-01T00:00:00+00:00",
    )
    _ok("evidence-bearing handoff validates", bool(validate_handoff(ready)), state)

    _ok(
        "READY_FOR_REVIEW without evidence is rejected",
        _raises(
            lambda: build_handoff(
                _mission(),
                attempt_id="attempt-2",
                worker_id="worker-1",
                status="READY_FOR_REVIEW",
                workspace_lease=_lease(),
                checks=({"name": "tests", "status": "PASS", "evidence_ref": ""},),
                next_safe_action="Collect evidence.",
            )
        ),
        state,
    )
    _ok(
        "SUCCEEDED is not a representable handoff status",
        _raises(
            lambda: build_handoff(
                _mission(),
                attempt_id="attempt-3",
                worker_id="worker-1",
                status="SUCCEEDED",
                workspace_lease=_lease(),
                next_safe_action="None.",
            )
        ),
        state,
    )

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
