#!/usr/bin/env python3
"""Focused tests for bounded, idempotent execution outcome envelopes."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.events import read_events
from skills.trajectory.outcome import STATUSES, emit_outcome, load_outcomes
from skills.trajectory.quality import load_verified


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== quality outcome envelope tests ==")

    with tempfile.TemporaryDirectory() as project:
        private_task = "summarize SECRET_OUTCOME_CANARY_1842 logs"
        first = emit_outcome(
            private_task,
            project_root=project,
            execution_id="mission-17/attempt-1",
            source="codex",
            route="local",
            status="partial",
            task_type="summary",
            permission_profile="workspace-write",
        )
        replay = emit_outcome(
            private_task,
            project_root=project,
            execution_id="mission-17/attempt-1",
            source="codex",
            route="local",
            status="partial",
            task_type="summary",
            permission_profile="workspace-write",
        )
        rows = load_outcomes(project)
        raw = (Path(project) / ".botte" / "quality-outcomes.jsonl").read_text(
            encoding="utf-8"
        )
        events = read_events(project)
        _ok("partial facts emit an unverified envelope",
            first["envelope"]["verification_state"] == "unverified"
            and first["trajectory"] is None, state)
        _ok("replay is idempotent in both envelope and event ledgers",
            replay["deduplicated"] and len(rows) == 1
            and len([e for e in events if e.get("kind") == "qa_outcome"]) == 1, state)
        _ok("raw task and execution IDs are never persisted",
            "SECRET_OUTCOME_CANARY_1842" not in raw
            and "mission-17/attempt-1" not in raw, state)
        _ok("public event omits task fingerprints and evidence references",
            all("task_fingerprint" not in event and "evidence_refs" not in event
                for event in events if event.get("kind") == "qa_outcome"), state)

    with tempfile.TemporaryDirectory() as project:
        rejected = emit_outcome(
            "classify the report",
            project_root=project,
            execution_id="self-report",
            source="local_model",
            route="local",
            status="pass",
            verified_by="model:self-report",
            evidence_refs=("model:confidence",),
        )
        missing = emit_outcome(
            "classify another report",
            project_root=project,
            execution_id="missing-evidence",
            source="ci",
            route="local",
            status="pass",
            verified_by="ci:unit",
        )
        _ok("model self-report is rejected rather than promoted",
            rejected["envelope"]["verification_state"] == "rejected"
            and rejected["trajectory"] is None, state)
        _ok("a verifier without evidence cannot create a label",
            missing["envelope"]["verification_state"] == "rejected"
            and not load_verified(project), state)

    with tempfile.TemporaryDirectory() as project:
        verified = emit_outcome(
            "parse the checked fixture",
            project_root=project,
            execution_id="ci-run-927/job-3",
            source="ci",
            route="deterministic",
            status="pass-robust",
            verified_by="ci:pytest",
            evidence_refs=("pytest:test_fixture", "schema:quality-output"),
            task_type="parse",
            tool_versions={"pytest": "9.0", "botte": "wave2"},
            duration_ms=42,
        )
        replay = emit_outcome(
            "parse the checked fixture",
            project_root=project,
            execution_id="ci-run-927/job-3",
            source="ci",
            route="deterministic",
            status="pass-robust",
            verified_by="ci:pytest",
            evidence_refs=("pytest:test_fixture", "schema:quality-output"),
            task_type="parse",
            tool_versions={"pytest": "9.0", "botte": "wave2"},
            duration_ms=42,
        )
        _ok("external evidence promotes exactly one verified trajectory",
            verified["trajectory"] is not None
            and verified["trajectory"]["outcome_id"] == verified["envelope"]["id"]
            and len(load_verified(project)) == 1, state)
        _ok("verified replay cannot inflate the quality ledger",
            replay["deduplicated"] and len(load_outcomes(project)) == 1
            and len(load_verified(project)) == 1, state)

    with tempfile.TemporaryDirectory() as project:
        for index, status in enumerate(STATUSES):
            emit_outcome(
                f"bounded lifecycle state {index}",
                project_root=project,
                execution_id=f"state-{index}",
                source="test",
                route="human" if status == "APPROVAL_REQUIRED" else "local",
                status=status,
            )
        loaded_statuses = {row["status"] for row in load_outcomes(project)}
        _ok("partial, failure, uncertainty, abstention, escalation and approval are representable",
            loaded_statuses == set(STATUSES), state)
        _ok("all lifecycle envelopes remain shadow-only and non-activating",
            all(row["shadow_only"] and not row["activation_allowed"]
                for row in load_outcomes(project)), state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
