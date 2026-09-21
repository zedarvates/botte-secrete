"""Execute a bounded Botte mission inside an expiring worktree lease."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

from skills.atomic_json import write_json
from skills.console_utf8 import force_utf8
from skills.meta_harness import MetaHarness
from skills.meta_harness.lease import WorkspaceLeaseError
from skills.meta_harness.review import ReviewError
from skills.run_contract import (
    ContractError,
    compile_context_manifest,
    load_mission,
    resume_base_ref,
)


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(prog="botte run", description=__doc__)
    parser.add_argument("mission", help="botte.mission/v1 JSON file")
    parser.add_argument("--project", default=".", help="Git project root")
    parser.add_argument("--plan", default="audit", help="Built-in MetaHarness plan")
    parser.add_argument("--worker-id", default="phaseone-worker")
    parser.add_argument("--attempt-id")
    parser.add_argument("--base-ref")
    parser.add_argument("--resume", help="Prior botte.handoff/v1 JSON")
    parser.add_argument("--workspace-root")
    parser.add_argument("--address-failure", action="append", default=[])
    parser.add_argument("--format", choices=["report", "json"], default="report")
    args = parser.parse_args(argv)

    try:
        mission = load_mission(args.mission)
        project = Path(args.project).resolve()
        manifest = compile_context_manifest(project, mission)
        base_ref = args.base_ref or "HEAD"
        if args.resume:
            try:
                prior_handoff = json.loads(Path(args.resume).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractError(f"cannot read resume handoff: {exc}") from exc
            resumed_sha = resume_base_ref(mission, prior_handoff)
            if args.base_ref and args.base_ref != resumed_sha:
                raise ContractError("--base-ref cannot override the handoff-bound resume SHA")
            base_ref = resumed_sha
        attempt_id = args.attempt_id or f"attempt-{uuid.uuid4().hex[:12]}"
        mission_key = hashlib.sha256(
            mission["mission_id"].encode("utf-8")
        ).hexdigest()[:24]
        run_dir = project / ".botte-cache" / "runs" / mission_key / attempt_id
        write_json(run_dir / "context-manifest.json", manifest)

        harness = MetaHarness(
            workdir=str(project),
            mission=mission,
            context_manifest=manifest,
            worker_id=args.worker_id,
            attempt_id=attempt_id,
            base_ref=base_ref,
            workspace_root=args.workspace_root,
            addressed_failure_refs=args.address_failure,
        )
        plans = harness.list_plans()
        if args.plan not in plans:
            raise ContractError(
                f"unknown built-in plan {args.plan}; choose one of {', '.join(plans)}"
            )
        plan = harness.plan(plans[args.plan])
        session = harness.execute(plan)
        write_json(run_dir / "handoff.json", session.handoff)
        if args.format == "json":
            print(session.to_json())
        else:
            print(session.report())
        return 0 if session.handoff and session.handoff["status"] in {
            "READY_FOR_REVIEW", "PARTIAL", "APPROVAL_REQUIRED"
        } else 1
    except (ContractError, WorkspaceLeaseError, ReviewError, ValueError) as exc:
        print(f"RUN BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
