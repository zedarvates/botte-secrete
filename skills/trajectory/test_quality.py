#!/usr/bin/env python3
"""Focused tests for the verified quality ledger and shadow k-NN baseline."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from skills.events import read_events
from skills.trajectory import cli
from skills.trajectory.quality import (
    advise_route,
    embed_task,
    load_verified,
    quality_status,
    record_verified,
)


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== quality compass tests ==")

    _ok("feature hashing is deterministic",
        embed_task("résume ce journal") == embed_task("résume ce journal"), state)

    with tempfile.TemporaryDirectory() as project:
        private_task = "summarize SECRET_CANARY_927 authentication failure log"
        first = record_verified(
            private_task,
            project_root=project,
            route="local",
            verdict="pass",
            verified_by="tests:pytest",
            task_type="summary",
            evidence_refs=("pytest:test_auth",),
        )
        ledger = Path(project) / ".botte" / "quality-trajectories.jsonl"
        raw = ledger.read_text(encoding="utf-8")
        _ok("record is verified and schema-versioned",
            first["verified"] is True and first["schema"].endswith("/v1"), state)
        _ok("raw task text is never persisted",
            "SECRET_CANARY_927" not in raw and first["raw_task_stored"] is False, state)
        _ok("quality outcome also reaches the event stream",
            any(event.get("kind") == "qa_trajectory" for event in read_events(project)), state)

        valid_count = len(load_verified(project))
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "schema": "botte.quality-trajectory/v1",
                "verified": True,
                "route": "local",
                "verdict": "PASS",
                "features": [[0, 1.0]],
            }) + "\n")
        _ok("malformed local rows are ignored rather than trusted",
            len(load_verified(project)) == valid_count, state)

        try:
            record_verified(
                "classify this",
                project_root=project,
                route="local",
                verdict="pass",
                verified_by="model-self-report",
            )
            blocked = False
        except ValueError:
            blocked = True
        _ok("model self-report cannot become a quality label", blocked, state)

        try:
            record_verified(
                "classify with no evidence",
                project_root=project,
                route="local",
                verdict="pass",
                verified_by="tests:pytest",
            )
            missing_evidence_blocked = False
        except ValueError:
            missing_evidence_blocked = True
        _ok("a verifier identity without evidence cannot create a label",
            missing_evidence_blocked, state)

        invalid_inputs = 0
        for bad in (
            {"task": None, "tags": ()},
            {"task": "valid task", "tags": "not-a-list"},
            {"task": "valid task", "tags": (), "quality_score": True},
        ):
            try:
                record_verified(
                    bad["task"],
                    project_root=project,
                    route="local",
                    verdict="pass",
                    verified_by="tests:pytest",
                    tags=bad["tags"],
                    quality_score=bad.get("quality_score"),
                )
            except ValueError:
                invalid_inputs += 1
        _ok("unbounded or mistyped public inputs fail closed", invalid_inputs == 3, state)

        collecting = advise_route("summarize another authentication log", project_root=project)
        _ok("k-NN abstains before the support floor",
            collecting.status == "collecting" and collecting.recommendation is None, state)

        local_tasks = [
            "summarize pytest failures from the login module",
            "summarize CI failure logs for authentication tests",
            "summarize a failing access-control test report",
            "summarize unit-test errors in the session handler",
        ]
        for task in local_tasks:
            record_verified(
                task,
                project_root=project,
                route="local",
                verdict="pass",
                verified_by="tests:pytest",
                task_type="summary",
                duration_ms=120,
                tokens=140,
                evidence_refs=("pytest:summary_route",),
            )
        for task in (
            "summarize complex authentication incident evidence",
            "summarize cross-service access-control incident logs",
        ):
            record_verified(
                task,
                project_root=project,
                route="cloud",
                verdict="pass-robust",
                verified_by="independent:review",
                task_type="summary",
                duration_ms=900,
                cost_usd=0.02,
                tokens=600,
                evidence_refs=("independent:summary_review",),
            )

        suggestion = advise_route(
            "summarize authentication test failure logs",
            project_root=project,
            task_type="summary",
        )
        _ok("k-NN chooses the cheapest sufficiently verified route",
            suggestion.status == "suggest" and suggestion.recommendation == "local", state)
        _ok("advice is explainable and never acts",
            suggestion.neighbors and suggestion.candidates
            and suggestion.shadow_only and not suggestion.acted
            and suggestion.calibrated is False, state)

        gated = advise_route(
            "deploy the authentication fix",
            project_root=project,
            risk="high",
        )
        _ok("high-impact work bypasses k-NN and keeps a human gate",
            gated.status == "gated" and gated.recommendation == "human"
            and gated.human_gate, state)

        duplicate_task = "repeatable formatter task"
        for verdict in ("pass", "pass-robust"):
            record_verified(
                duplicate_task,
                project_root=project,
                route="deterministic",
                verdict=verdict,
                verified_by="deterministic:roundtrip",
                evidence_refs=("deterministic:roundtrip",),
            )
        status = quality_status(project)
        _ok("duplicate task/route rows do not inflate grounding progress",
            status["recorded_outcomes"] == len(load_verified(project))
            and status["verified_samples"] == status["recorded_outcomes"] - 1
            and status["grounding_deduplication"] == "latest_per_task_route", state)
        _ok("status exposes one next step and keeps activation blocked",
            bool(status["next_action"]) and status["activation_allowed"] is False, state)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main(["status", project, "--json"])
        payload = json.loads(stdout.getvalue())
        _ok("the top-level QA status is machine-readable",
            rc == 0 and payload["mode"] == "shadow", state)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([
                "summarize authentication failure logs",
                "--project", project,
                "--task-type", "summary",
                "--json",
            ])
        payload = json.loads(stdout.getvalue())
        _ok("a bare task uses the intuitive advise shortcut",
            rc == 0 and payload["status"] == "suggest", state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
