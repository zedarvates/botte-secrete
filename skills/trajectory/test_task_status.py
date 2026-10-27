#!/usr/bin/env python3
"""Focused tests for passive Kanboard/task-plane status consumption."""

from __future__ import annotations

import json
import tempfile

from skills.llm_mcp.server import handle
from skills.trajectory.outcome import emit_outcome
from skills.trajectory.task_status import task_quality_status


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _emit(project: str, *, execution_id: str, status: str,
          verified_by: str = "", evidence_refs=(), **flags) -> dict:
    return emit_outcome(
        "PRIVATE_TASK_CANARY must never reach Kanboard",
        project_root=project,
        execution_id=execution_id,
        source="codex",
        route="human" if status == "APPROVAL_REQUIRED" else "deterministic",
        status=status,
        verified_by=verified_by,
        evidence_refs=evidence_refs,
        approval_required=flags.get("approval_required", False),
    )


def main() -> int:
    state = [0, 0]
    print("== passive task-plane quality status tests ==")

    with tempfile.TemporaryDirectory() as project:
        empty = task_quality_status(task_ref="kanboard:task:76", project_root=project)
        _ok("empty ledger yields a non-terminal review observation",
            empty["state"] == "empty" and empty["outcome_id"] is None
            and empty["suggested_task_state"] == "review"
            and empty["task_transition_allowed"] is False
            and empty["terminal"] is False, state)

        partial = _emit(project, execution_id="PRIVATE_EXECUTION_CANARY",
                        status="PARTIAL", evidence_refs=("agent:self-report",))
        packet = task_quality_status(task_ref="kanboard:task:76", project_root=project)
        encoded = json.dumps(packet)
        _ok("unverified observation exports no evidence reference",
            packet["state"] == "collecting" and packet["verified"] is False
            and packet["evidence_refs"] == [], state)
        _ok("packet omits raw task, execution IDs, and private fingerprints",
            "PRIVATE_TASK_CANARY" not in encoded
            and "PRIVATE_EXECUTION_CANARY" not in encoded
            and "task_fingerprint" not in packet
            and "execution_fingerprint" not in packet, state)
        _ok("same task and outcome replay to the same passive packet",
            packet == task_quality_status(
                task_ref="kanboard:task:76", project_root=project,
                outcome_id=partial["envelope"]["id"],
            ), state)

    with tempfile.TemporaryDirectory() as project:
        passed = _emit(
            project, execution_id="verified-pass", status="PASS_ROBUST",
            verified_by="tests:pytest", evidence_refs=("pytest:test_task",),
        )
        packet = task_quality_status(task_ref="kanboard:job:91", project_root=project)
        _ok("verified pass exposes references but never closes a task",
            packet["state"] == "grounded" and packet["verified"] is True
            and packet["evidence_refs"] == ["pytest:test_task"]
            and packet["suggested_task_state"] == "review"
            and packet["terminal"] is False, state)

        _emit(
            project, execution_id="verified-fail", status="FAIL",
            verified_by="tests:pytest", evidence_refs=("pytest:test_failure",),
        )
        latest = task_quality_status(task_ref="kanboard:job:91", project_root=project)
        selected = task_quality_status(
            task_ref="kanboard:job:91", project_root=project,
            outcome_id=passed["envelope"]["id"],
        )
        _ok("latest verified failure remains in review without authorizing mutation",
            latest["state"] == "failing"
            and latest["suggested_task_state"] == "review"
            and latest["task_transition_allowed"] is False, state)
        _ok("consumer can select one outcome deterministically",
            selected["outcome_id"] == passed["envelope"]["id"]
            and selected["state"] == "grounded", state)

    with tempfile.TemporaryDirectory() as project:
        _emit(
            project, execution_id="approval", status="APPROVAL_REQUIRED",
            approval_required=True,
        )
        approval = task_quality_status(task_ref="kanboard:task:5", project_root=project)
        _ok("approval-required remains explicitly human-gated",
            approval["state"] == "approval_required"
            and approval["requires_human_review"] is True
            and approval["activation_allowed"] is False, state)

    with tempfile.TemporaryDirectory() as project:
        _emit(project, execution_id="abstention", status="ABSTAINED")
        abstained = task_quality_status(task_ref="kanboard:task:8", project_root=project)
        _ok("abstention remains visible without becoming a label",
            abstained["state"] == "abstained"
            and abstained["verified"] is False
            and abstained["evidence_refs"] == [], state)

    with tempfile.TemporaryDirectory() as project:
        _emit(project, execution_id="escalation", status="ESCALATED")
        escalated = task_quality_status(task_ref="kanboard:task:9", project_root=project)
        _ok("escalation stays non-terminal and human-reviewed",
            escalated["state"] == "escalated"
            and escalated["terminal"] is False
            and escalated["requires_human_review"] is True, state)

    with tempfile.TemporaryDirectory() as project:
        _emit(
            project, execution_id="uncertain", status="UNCERTAIN",
            verified_by="tests:pytest", evidence_refs=("pytest:uncertain",),
        )
        uncertain = task_quality_status(task_ref="kanboard:task:10", project_root=project)
        _ok("verified uncertainty asks for replay rather than completion",
            uncertain["state"] == "uncertain"
            and uncertain["evidence_refs"] == ["pytest:uncertain"]
            and uncertain["suggested_task_state"] == "review", state)

    with tempfile.TemporaryDirectory() as project:
        _emit(
            project, execution_id="self-pass", status="PASS",
            verified_by="model:self-report", evidence_refs=("model:confidence",),
        )
        rejected = task_quality_status(task_ref="kanboard:task:6", project_root=project)
        _ok("agent self-report cannot appear as Kanboard evidence",
            rejected["verification_state"] == "rejected"
            and rejected["verified"] is False
            and rejected["evidence_refs"] == [], state)

        response = handle({
            "jsonrpc": "2.0", "id": 76, "method": "tools/call",
            "params": {"name": "qa_task_status", "arguments": {
                "project": project, "task_ref": "kanboard:task:6",
            }},
        })
        payload = json.loads(response["result"]["content"][0]["text"])
        _ok("MCP exposes the same passive contract to Kanboard/Odin",
            payload == rejected and payload["schema"] == "botte.task-quality-status/v1",
            state)

    invalid_ref = missing_id = False
    try:
        task_quality_status(task_ref="raw task text with spaces")
    except ValueError:
        invalid_ref = True
    with tempfile.TemporaryDirectory() as project:
        try:
            task_quality_status(
                task_ref="kanboard:task:7", project_root=project,
                outcome_id="qo_0000000000000000",
            )
        except ValueError:
            missing_id = True
    _ok("raw-looking task references are rejected", invalid_ref, state)
    _ok("unknown outcome IDs fail closed", missing_id, state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
