#!/usr/bin/env python3
"""Focused tests for bounded Codex/Hermes run manifests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.events import read_events
from skills.hermes_bridge.bridge import dispatch
from skills.llm_mcp.server import handle
from skills.trajectory.agent_run import emit_agent_run
from skills.trajectory.outcome import load_outcomes
from skills.trajectory.quality import load_verified


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _manifest(agent: str = "codex", **updates) -> dict:
    manifest = {
        "schema": "botte.agent-run/v1",
        "agent": agent,
        "execution_id": "private-run/codex-17",
        "task": "inspect SECRET_AGENT_RUN_CANARY_761",
        "task_type": "code_review",
        "route": "cloud",
        "status": "PARTIAL",
        "model": "agent-model",
        "permission_profile": "workspace-write",
        "tool_versions": {"agent": "1.0"},
        "duration_ms": 12.5,
        "tokens": 21,
        "acted": True,
    }
    manifest.update(updates)
    return manifest


def main() -> int:
    state = [0, 0]
    print("== Codex/Hermes agent-run manifest tests ==")

    with tempfile.TemporaryDirectory() as project:
        first = emit_agent_run(_manifest(), project_root=project)
        replay = emit_agent_run(_manifest(), project_root=project)
        rows = load_outcomes(project)
        raw = (Path(project) / ".botte" / "quality-outcomes.jsonl").read_text(
            encoding="utf-8"
        )
        _ok("Codex partial manifest emits one unverified envelope",
            len(rows) == 1 and rows[0]["source"] == "codex"
            and rows[0]["status"] == "PARTIAL"
            and rows[0]["verification_state"] == "unverified"
            and first["trajectory"] is None, state)
        _ok("stable execution replay is idempotent",
            replay["deduplicated"] is True and len(rows) == 1, state)
        _ok("raw task and execution id never enter private storage",
            "SECRET_AGENT_RUN_CANARY_761" not in raw
            and "private-run/codex-17" not in raw, state)
        _ok("compact events omit task and evidence detail",
            all("task_fingerprint" not in event and "evidence_refs" not in event
                and "SECRET_AGENT_RUN_CANARY_761" not in json.dumps(event)
                for event in read_events(project)), state)
        _ok("agent facts remain shadow-only with activation blocked",
            rows[0]["shadow_only"] is True
            and rows[0]["activation_allowed"] is False, state)

    with tempfile.TemporaryDirectory() as project:
        self_report = emit_agent_run(_manifest(
            status="PASS", verdict="PASS", verified_by="codex:self-report",
            evidence_refs=["codex:confidence"],
        ), project_root=project)
        _ok("Codex self-report is rejected as a verified label",
            self_report["envelope"]["verification_state"] == "rejected"
            and self_report["trajectory"] is None
            and not load_verified(project), state)

    with tempfile.TemporaryDirectory() as project:
        verified = _manifest(
            agent="hermes", execution_id="hermes-run-3", route="local",
            status="PASS_ROBUST", verdict="PASS_ROBUST",
            verified_by="tests:pytest", evidence_refs=["pytest:test_agent_run"],
            quality_score=0.95,
        )
        first = emit_agent_run(verified, project_root=project)
        replay = emit_agent_run(verified, project_root=project)
        _ok("independent evidence promotes exactly one Hermes label",
            first["trajectory"] is not None and replay["deduplicated"] is True
            and len(load_verified(project)) == 1, state)

    rejected = False
    try:
        emit_agent_run({**_manifest(), "response": "must not be stored"})
    except ValueError:
        rejected = True
    _ok("unknown raw-output fields are rejected", rejected, state)

    with tempfile.TemporaryDirectory() as project:
        approval = emit_agent_run(_manifest(
            agent="hermes", execution_id="approval-7", route="human",
            status="APPROVAL_REQUIRED", acted=False, approval_required=True,
        ), project_root=project)
        _ok("approval-required state is preserved without a label",
            approval["envelope"]["approval_required"] is True
            and approval["trajectory"] is None, state)

    with tempfile.TemporaryDirectory() as project:
        mcp_call = handle({
            "jsonrpc": "2.0", "id": 91, "method": "tools/call",
            "params": {"name": "qa_agent_run", "arguments": {
                "project": project,
                "manifest": _manifest(execution_id="mcp-run-91"),
            }},
        })
        payload = json.loads(mcp_call["result"]["content"][0]["text"])
        _ok("Codex-compatible MCP surface reaches the shared adapter",
            payload["agent"] == "codex"
            and payload["envelope"]["source"] == "codex", state)

    with tempfile.TemporaryDirectory() as project:
        payload = json.loads(dispatch("botte_qa_agent_run", {
            "project": project,
            "manifest": _manifest(agent="hermes", execution_id="hermes-dispatch-2"),
        }))
        _ok("Hermes function bridge reaches the same adapter",
            payload["agent"] == "hermes"
            and payload["envelope"]["source"] == "hermes", state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
