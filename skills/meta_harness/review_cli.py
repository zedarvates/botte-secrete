"""Replay a handoff in a fresh worktree and emit an independent review."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from skills.atomic_json import write_json
from skills.console_utf8 import force_utf8
from skills.meta_harness import MetaHarness
from skills.meta_harness.lease import WorktreeLeaseManager, WorkspaceLeaseError
from skills.meta_harness.review import (
    CheckpointRegistry,
    ReviewError,
    review_handoff,
)
from skills.run_contract import ContractError, load_mission, resume_base_ref, validate_handoff
from skills.trajectory.outcome import emit_outcome


_REVIEW_PLANS = {"test-only", "audit", "security", "migration-gate"}


def _load_handoff(path: str) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read handoff: {exc}") from exc
    return validate_handoff(payload)


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(prog="botte review", description=__doc__)
    parser.add_argument("mission")
    parser.add_argument("handoff")
    parser.add_argument("--project", default=".")
    parser.add_argument("--reviewer-id", default="phasetwo-gauntlet")
    parser.add_argument("--plan", choices=sorted(_REVIEW_PLANS), default="test-only")
    parser.add_argument("--workspace-root")
    parser.add_argument("--previous-failure", action="append", default=[])
    parser.add_argument("--closed-failure", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    manager = None
    lease = None
    try:
        mission = load_mission(args.mission)
        handoff = _load_handoff(args.handoff)
        base_sha = resume_base_ref(mission, handoff)
        project = Path(args.project).resolve()
        manager = WorktreeLeaseManager(project, workspace_root=args.workspace_root)
        lease = manager.create(
            args.reviewer_id,
            base_ref=base_sha,
            ttl_seconds=mission["budgets"]["max_wall_seconds"] + 300,
        )

        replay = MetaHarness(workdir=lease.workspace_path)
        plan = replay.plan(replay.list_plans()[args.plan])
        session = replay.execute(plan)
        lease = manager.refresh(lease)
        checks = []
        for index, (result, step) in enumerate(zip(session.results, plan.steps)):
            status = {
                "passed": "PASS", "failed": "FAIL", "skipped": "SKIPPED",
            }.get(result.status, "UNCERTAIN")
            checks.append({
                "name": step.agent,
                "status": status,
                "evidence_ref": (
                    step.evidence_ref
                    or f"review:{session.name}:step-{index}:{step.agent}"
                ),
            })

        review = review_handoff(
            mission,
            handoff,
            reviewer_id=args.reviewer_id,
            review_workspace_lease=lease.contract_view(),
            replayed_checks=checks,
            previous_failure_refs=args.previous_failure,
            closed_failure_refs=args.closed_failure,
        )
        CheckpointRegistry(project).record_review(review)
        key = hashlib.sha256(mission["mission_id"].encode("utf-8")).hexdigest()[:24]
        default_output = (
            project / ".botte-cache" / "reviews" / key
            / f"{review['review_sha256']}.json"
        )
        output = Path(args.output) if args.output else default_output
        write_json(output, review)
        command_basis = json.dumps(
            [step.command + step.args for step in plan.steps],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        outcome_status = {
            "ACCEPT": "PASS",
            "REWORK": "FAIL",
            "BLOCKED": (
                "APPROVAL_REQUIRED"
                if review["approval_required"]
                else "UNCERTAIN"
            ),
        }[review["verdict"]]
        outcome_verdict = {
            "ACCEPT": "PASS",
            "REWORK": "FAIL",
            "BLOCKED": None,
        }[review["verdict"]]
        risk = {
            "R0": "low", "R1": "low", "R2": "standard",
            "R3": "high", "R4": "critical",
        }[mission["risk"]]
        emit_outcome(
            mission["objective"],
            project_root=project,
            execution_id=review["review_sha256"],
            source="gauntlet",
            route="deterministic",
            status=outcome_status,
            verdict=outcome_verdict,
            verified_by="independent:gauntlet",
            evidence_refs=review["evidence_refs"],
            risk=risk,
            permission_profile="shadow",
            harness="meta-harness/gauntlet-v1",
            approval_required=review["approval_required"],
            mission_id=mission["mission_id"],
            attempt_id=handoff["attempt_id"],
            worker_id=args.reviewer_id,
            workspace_lease=lease.contract_view(),
            repository_ref=replay._repository_ref(),
            base_sha=lease.base_sha,
            head_sha=lease.head_sha,
            dirty_tree_sha256=lease.dirty_tree_sha256,
            check_command_sha256=hashlib.sha256(
                command_basis.encode("utf-8")
            ).hexdigest(),
            checks=checks,
            artifacts=({
                "kind": "gauntlet-review",
                "ref": f"review:{review['review_sha256']}",
                "sha256": review["review_sha256"],
            },),
            uncertainties=(
                review["reasons"] if review["verdict"] != "ACCEPT" else ()
            ),
            review_verdict=review["verdict"],
            next_safe_action=review["next_safe_action"],
        )
        print(json.dumps(review, ensure_ascii=False, indent=2))
        return {"ACCEPT": 0, "REWORK": 1, "BLOCKED": 2}[review["verdict"]]
    except (ContractError, WorkspaceLeaseError, ReviewError, ValueError) as exc:
        print(f"REVIEW BLOCKED: {exc}", file=sys.stderr)
        return 2
    finally:
        if manager is not None and lease is not None:
            try:
                manager.release(lease)
            except WorkspaceLeaseError:
                try:
                    manager.quarantine(lease)
                except WorkspaceLeaseError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
