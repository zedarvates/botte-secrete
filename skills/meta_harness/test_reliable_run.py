#!/usr/bin/env python3
"""Integration tests for worktree leases, handoffs and Gauntlet review."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skills.meta_harness import MetaHarness, PipelinePlan, Step
from skills.meta_harness.lease import WorktreeLeaseManager
from skills.meta_harness.review import (
    CheckpointRegistry,
    ReviewError,
    review_handoff,
)
from skills.run_contract import build_handoff, resume_base_ref
from skills.trajectory.outcome import load_outcomes


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _raises(callable_, error=Exception) -> bool:
    try:
        callable_()
    except error:
        return True
    return False


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(
        list(args), cwd=root, capture_output=True, text=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    _run(root, "git", "init", "-b", "main")
    _run(root, "git", "config", "user.name", "Botte Test")
    _run(root, "git", "config", "user.email", "botte@example.invalid")
    (root / ".botte").mkdir()
    (root / ".botte" / "policy.md").write_text("no publish", encoding="utf-8")
    (root / "AGENTS.md").write_text("run tests", encoding="utf-8")
    (root / "README.md").write_text("fixture", encoding="utf-8")
    _run(root, "git", "add", ".")
    _run(root, "git", "commit", "-m", "fixture")


def _mission(**overrides) -> dict:
    mission = {
        "schema": "botte.mission/v1",
        "mission_id": "reliable-run-pilot",
        "objective": "Produce evidence in an isolated worktree.",
        "scope": {"include": ["src"], "exclude": ["private"]},
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
            "max_wall_seconds": 300,
            "max_revisions": 2,
        },
        "required_evidence": ["tests:project"],
        "approval_gates": [],
        "rollback": {"required": False, "snapshot_ref": ""},
        "context": {
            "budget_tokens": 2000,
            "required_files": ["README.md"],
            "optional_files": [],
        },
    }
    mission.update(overrides)
    return mission


def _review_lease(worker: str, fingerprint: str) -> dict:
    return {
        "lease_id": "wl_" + ("1" if worker == "phaseone" else "2") * 16,
        "worker_id": worker,
        "state": "ACTIVE",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "expires_at": "2026-09-02T00:00:00+00:00",
        "workspace_fingerprint": fingerprint,
    }


def main() -> int:
    state = [0, 0]
    print("== reliable run tests ==")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        root.mkdir()
        _init_repo(root)
        worktrees = Path(directory) / "worktrees"
        manager = WorktreeLeaseManager(root, workspace_root=worktrees)

        with ThreadPoolExecutor(max_workers=10) as pool:
            leases = list(
                pool.map(
                    lambda index: manager.create(
                        f"worker-{index}", ttl_seconds=300
                    ),
                    range(20),
                )
            )
        _ok("20 parallel workers receive collision-free lease IDs",
            len({lease.lease_id for lease in leases}) == 20, state)
        _ok("20 parallel workers receive distinct worktrees",
            len({lease.workspace_path for lease in leases}) == 20
            and all(Path(lease.workspace_path).is_dir() for lease in leases), state)
        _ok("lease contract views expose no machine paths",
            all("workspace_path" not in lease.contract_view() for lease in leases), state)

        with ThreadPoolExecutor(max_workers=10) as pool:
            released = list(pool.map(manager.release, leases))
        _ok("clean parallel worktrees release without collision",
            all(lease.state == "RELEASED" for lease in released), state)

        source = manager.create("resume-source", ttl_seconds=300)
        source_handoff = build_handoff(
            _mission(),
            attempt_id="resume-source",
            worker_id="resume-source",
            status="READY_FOR_REVIEW",
            workspace_lease=source.contract_view(),
            checks=({
                "name": "project-tests", "status": "PASS",
                "evidence_ref": "tests:project",
            },),
            evidence_refs=("tests:project",),
            next_safe_action="Resume in a fresh leased workspace.",
        )
        resume_sha = resume_base_ref(_mission(), source_handoff)
        manager.release(source)
        resumed = [
            manager.create(f"resume-{index}", base_ref=resume_sha, ttl_seconds=300)
            for index in range(5)
        ]
        _ok("5/5 fresh-session resumptions bind to the handoff SHA",
            all(lease.base_sha == resume_sha for lease in resumed), state)
        for lease in resumed:
            manager.release(lease)

        dirty = manager.create("dirty-worker", ttl_seconds=300)
        (Path(dirty.workspace_path) / "uncommitted.txt").write_text(
            "preserve me", encoding="utf-8"
        )
        quarantined = manager.release(dirty)
        _ok("dirty release is quarantined instead of deleted",
            quarantined.state == "QUARANTINED"
            and Path(quarantined.workspace_path).exists(), state)

    author_lease = _review_lease("phaseone", "c" * 64)
    handoff = build_handoff(
        _mission(),
        attempt_id="attempt-1",
        worker_id="phaseone",
        status="READY_FOR_REVIEW",
        workspace_lease=author_lease,
        checks=({
            "name": "project-tests", "status": "PASS",
            "evidence_ref": "tests:project",
        },),
        evidence_refs=("tests:project",),
        next_safe_action="Independent review.",
    )
    review = review_handoff(
        _mission(),
        handoff,
        reviewer_id="phasetwo",
        review_workspace_lease=_review_lease("phasetwo", "d" * 64),
        replayed_checks=({
            "name": "project-tests-replay", "status": "PASS",
            "evidence_ref": "replay:project-tests",
        },),
    )
    _ok("fresh independent workspace can ACCEPT verified evidence",
        review["verdict"] == "ACCEPT", state)
    _ok("author cannot review its own handoff",
        _raises(lambda: review_handoff(
            _mission(), handoff,
            reviewer_id="phaseone",
            review_workspace_lease=_review_lease("phaseone", "e" * 64),
            replayed_checks=({
                "name": "tests", "status": "PASS", "evidence_ref": "replay:tests"
            },),
        ), ReviewError), state)
    high_risk_blocked = []
    for risk in ("R3", "R4"):
        high_mission = _mission(risk=risk, approval_gates=["owner-review"])
        high_handoff = build_handoff(
            high_mission,
            attempt_id=f"attempt-{risk}",
            worker_id="phaseone",
            status="READY_FOR_REVIEW",
            workspace_lease=author_lease,
            checks=({
                "name": "project-tests", "status": "PASS",
                "evidence_ref": "tests:project",
            },),
            evidence_refs=("tests:project",),
            approval_required=True,
            next_safe_action="Owner review.",
        )
        high_review = review_handoff(
            high_mission,
            high_handoff,
            reviewer_id="phasetwo",
            review_workspace_lease=_review_lease("phasetwo", "d" * 64),
            replayed_checks=({
                "name": "project-tests-replay", "status": "PASS",
                "evidence_ref": "replay:project-tests",
            },),
        )
        high_risk_blocked.append(high_review["verdict"] == "BLOCKED")
    _ok("R3/R4 remain blocked without owner authorization",
        all(high_risk_blocked), state)

    with tempfile.TemporaryDirectory() as directory:
        registry = CheckpointRegistry(directory)
        registry.register_attempt(_mission(), attempt_id="attempt-1")
        accepted = registry.record_review(review)
        green = dict(accepted["best_known_green"])
        failed = dict(review)
        failed.pop("review_sha256")
        failed["verdict"] = "REWORK"
        failed["reasons"] = ["independent_replay_failed"]
        from skills.run_contract import contract_fingerprint
        failed["review_sha256"] = contract_fingerprint(failed)
        after_failure = registry.record_review(failed)
        _ok("unaccepted revision cannot overwrite best-known-green",
            after_failure["best_known_green"] == green, state)
        registry.register_attempt(
            _mission(), attempt_id="attempt-2", addressed_failure_refs=["test:red"]
        )
        registry.register_attempt(
            _mission(), attempt_id="attempt-3", addressed_failure_refs=["test:red"]
        )
        _ok("per-finding revision budget stops a third retry",
            _raises(lambda: registry.register_attempt(
                _mission(), attempt_id="attempt-4",
                addressed_failure_refs=["test:red"],
            ), ReviewError), state)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        root.mkdir()
        _init_repo(root)
        harness = MetaHarness(
            workdir=str(root),
            mission=_mission(),
            worker_id="phaseone",
            workspace_root=Path(directory) / "run-worktrees",
        )
        plan = PipelinePlan(
            name="proof",
            steps=[Step(
                agent="proof",
                command=[sys.executable, "-c", "print('proof')"],
                evidence_ref="tests:project",
            )],
        )
        session = harness.execute(plan)
        _ok("mission execution emits READY_FOR_REVIEW handoff",
            session.handoff["status"] == "READY_FOR_REVIEW", state)
        _ok("session persists lease identity without raw path",
            "workspace_path" not in session.to_json()
            and session.workspace_lease["lease_id"], state)
        outcomes = load_outcomes(root)
        _ok("mission run emits a Git-bound private outcome envelope",
            len(outcomes) == 1
            and outcomes[0]["mission_id"] == "reliable-run-pilot"
            and outcomes[0]["head_sha"] == session.workspace_lease["head_sha"]
            and outcomes[0]["id"] == session.outcome_id, state)
        released = harness.lease_manager.release(harness.workspace_lease)
        _ok("explicit clean release succeeds", released.state == "RELEASED", state)

        blocked = MetaHarness(
            workdir=str(root),
            mission=_mission(),
            worker_id="shadow-worker",
            workspace_root=Path(directory) / "blocked-worktrees",
        )
        _ok("SHADOW mission rejects mutating agents before creating a lease",
            _raises(lambda: blocked.plan(["dartagnan"]), ValueError), state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
