"""CLI for the Conductor.

    python -m skills.conductor.cli "<goal>" [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.conductor import plan, run_goal


def _save_report(kind: str, report: dict, args) -> None:
    import os
    import tempfile
    from pathlib import Path
    from skills.report import save, timestamped_name
    if args.effects or args.review_effects or args.stop_on_failure:
        from skills.atomic_json import write_json
        directory = Path(".botte") / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        prefix = Path(timestamped_name(f"{kind}-effects", "json")).stem + "-"
        fd, name = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=directory)
        os.close(fd)
        target = Path(name)
        # tempfile may return an absolute path; consumers use a project-relative reference.
        report["effects_json"] = (directory / target.name).as_posix()
        try:
            write_json(target, report)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    save(kind, report, fmt=args.save, out_dir=Path(".botte") / "reports",
         title=f"{kind.title()} — {report['goal']}")


def _run_execute(args) -> int:
    r = run_goal(args.goal, confirm=args.confirm, dry_run=args.dry_run,
                 timeout=args.timeout, include_effects=args.effects,
                 observe_effects=args.observe_effects, review_effects=args.review_effects,
                 stop_on_failure=args.stop_on_failure)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.save:
        _save_report("execution", r, args)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1 if r["summary"]["failed"] else 0

    c = r["summary"]
    print(f"🎬 Executed plan for: {r['goal']}")
    print(f"   mode: {r['mode']}  ·  ran {c['ran']} · blocked {c['blocked']} · "
          f"skipped {c['skipped']} · failed {c['failed']}\n")
    icon = {"ran": "✅", "failed": "❌", "blocked": "🔒", "skipped": "⏭️"}
    for s in r["results"]:
        print(f"   {icon.get(s['status'], '•')} {s['capability']:18} [{s['status']}] "
              f"{s['command']}")
        print(f"        {s['note']}")
        if "effects_before" in s:
            print(f"        effects before execution: {s['effects_before']['status']} "
                  "(declaration only; see --json for details)")
        if "effects_summary" in s:
            e = s["effects_summary"]
            print(f"        observed: {e['calls']} calls, {e['deviations']} write deviations, "
                  f"{e['unfinished_calls']} unfinished calls, "
                  f"{e['network_attempts']} network attempts; coverage partial (see --json)")
        if "review_after" in s:
            e = s["review_after"]
            print(f"        review: {e['coverage']} · {e['task_outcome']} · {e['next_action']}")
    if "effects_json" in r:
        print(f"   Saved JSON report: {r['effects_json']}")
    # a failed step is a non-zero exit so callers/CI can react
    return 1 if c["failed"] else 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="conductor", description=__doc__)
    p.add_argument("goal", nargs="?")
    p.add_argument("--plan", help="explicit botte.skill-plan/v1 JSON; preview unless --execute")
    comparisons = p.add_mutually_exclusive_group()
    comparisons.add_argument("--compare-plans", metavar="JSON", help="compare supplied plans using user preferences; no execution")
    comparisons.add_argument("--propose-plans", metavar="JSON", help="offer supplied plans for user choice; no selection or execution")
    comparisons.add_argument("--select-plan", metavar="JSON", help="bind a declared candidate choice to this request; no execution")
    comparisons.add_argument("--prepare-plan-handoff", metavar="JSON", help="bind a selection to a supplied Conductor plan; no execution")
    comparisons.add_argument("--build-plan-candidates", metavar="JSON", help="build bounded alternatives from explicit goal recipes; no execution")
    p.add_argument("--candidate", help="candidate ID for --select-plan")
    p.add_argument("--input-digest", help="displayed input digest for --select-plan")
    p.add_argument("--selection", metavar="JSON", help="selection receipt for --prepare-plan-handoff")
    p.add_argument("--execution-plan", metavar="JSON", help="supplied botte.skill-plan/v1 for --prepare-plan-handoff")
    p.add_argument("--project", default=".", help="project root for an explicit plan")
    p.add_argument("--checkpoint", help="project-relative private skill-run JSON checkpoint")
    p.add_argument("--resume", action="store_true", help="resume unstarted work from --checkpoint")
    p.add_argument("--json", action="store_true")
    p.add_argument("--effects", action="store_true",
                   help="include selected capabilities' effects declarations; no extra authority")
    p.add_argument("--review-effects", action="store_true",
                   help="add compact shared review cues before/after; no model call or automatic observation")
    p.add_argument("--observe-effects", action="store_true",
                   help="with --execute, collect partial effect evidence and call links; implies --effects")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped plan or execution report under ./.botte/reports/")
    p.add_argument("--execute", action="store_true",
                   help="run the plan's read-only steps (mutating/cloud steps are gated)")
    p.add_argument("--confirm", action="store_true",
                   help="with --execute, also run the gated (mutating/cloud) steps")
    p.add_argument("--dry-run", action="store_true",
                   help="with --execute, classify every step but run nothing")
    p.add_argument("--stop-on-failure", action="store_true",
                   help="with --execute, skip all remaining steps after a nonzero exit; no output verification")
    p.add_argument("--timeout", type=int, default=120,
                   help="per-step timeout in seconds (default 120)")
    args = p.parse_args(argv)
    modes = (args.compare_plans, args.propose_plans, args.select_plan,
             args.prepare_plan_handoff, args.build_plan_candidates)
    if any(value is not None for value in modes):
        if (args.goal is not None or args.plan is not None or args.execute or args.confirm or args.dry_run
                or args.checkpoint is not None or args.resume or args.effects or args.review_effects
                or args.observe_effects or args.save or args.stop_on_failure
                or args.project != "." or args.timeout != 120):
            p.error("plan construction, comparison, proposal, selection or handoff is a separate read-only operation; execution flags are unavailable")
        selecting = args.select_plan is not None
        preparing = args.prepare_plan_handoff is not None
        building = args.build_plan_candidates is not None
        if selecting:
            if args.candidate is None or args.input_digest is None or args.selection is not None or args.execution_plan is not None:
                p.error("--select-plan requires --candidate and --input-digest only")
        elif preparing:
            if args.selection is None or args.execution_plan is None or args.candidate is not None or args.input_digest is not None:
                p.error("--prepare-plan-handoff requires --selection and --execution-plan only")
        elif any(value is not None for value in (args.candidate, args.input_digest, args.selection, args.execution_plan)):
            p.error("selection arguments require --select-plan or --prepare-plan-handoff")
        from pathlib import Path
        from skills.conductor.preferences import MAX_INPUT_BYTES, parse_request_json, propose_plans, rank_plans
        proposing = args.propose_plans is not None
        source = next(value for value in modes if value is not None)

        def read_object(path):
            with Path(path).open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                raise ValueError("plan document exceeds size limit")
            return parse_request_json(raw.decode("utf-8"))

        try:
            request = read_object(source)
            if selecting:
                from skills.conductor.selection import select_plan
                result = select_plan(request, args.candidate, args.input_digest)
            elif preparing:
                from skills.conductor.handoff import prepare_plan_handoff
                result = prepare_plan_handoff(request, read_object(args.selection), read_object(args.execution_plan))
            elif building:
                from skills.conductor.recipes import build_plan_candidates
                result = build_plan_candidates(request)
            else:
                operation = propose_plans if proposing else rank_plans
                result = operation(request)
        except (OSError, ValueError, RecursionError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=True))
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if selecting or preparing or result["status"] in ("ranked", "proposed", "candidates_built") else 2
    if any(value is not None for value in (args.candidate, args.input_digest, args.selection, args.execution_plan)):
        p.error("selection arguments require --select-plan or --prepare-plan-handoff")
    if args.stop_on_failure and not args.execute:
        p.error("--stop-on-failure requires --execute")
    if args.observe_effects:
        if not args.execute:
            p.error("--observe-effects requires --execute")
        args.effects = True

    if args.plan:
        if args.review_effects or args.stop_on_failure:
            p.error("--plan does not support --review-effects or --stop-on-failure; use explicit dependency checks")
        if args.goal or args.save or args.effects:
            p.error("--plan has its own goal and effects; use --checkpoint to retain its report")
        from skills.conductor.verified import execute_verified, read_document
        try:
            explicit = read_document(args.plan)
            r = execute_verified(explicit, cwd=args.project, confirm=args.confirm,
                                 dry_run=args.dry_run or not args.execute, timeout=args.timeout,
                                 checkpoint=args.checkpoint, resume=args.resume)
        except (OSError, ValueError) as exc:
            r = {"error": str(exc)}
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1 if "error" in r or (r["mode"] != "dry_run" and not r["complete"]) else 0
    if not args.goal or args.checkpoint or args.resume or args.project != ".":
        p.error("provide a goal, or use --plan for checkpointed execution")

    if args.execute:
        return _run_execute(args)

    r = plan(args.goal, include_effects=args.effects, review_effects=args.review_effects)
    if args.save and "error" not in r:
        _save_report("plan", r, args)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    print(f"🎯 Goal: {r['goal']}")
    print(f"   effort: {r['effort']['tier']}  ·  plan cost: {r['cloud_tokens']} cloud tokens\n")
    for s in r["steps"]:
        tag = "local" if s["local"] else "local→cloud"
        print(f"   {s['order']}. [{s['layer']:8}] {s['capability']:18} ({tag})")
        print(f"        {s['command']}")
        print(f"        why: {s['why'][:90]}")
        if "effects" in s:
            print(f"        effects: {s['effects']['status']} "
                  "(declaration only; see --json for details)")
        if "review_before" in s:
            e = s["review_before"]
            print(f"        review: {e['declaration']} · operation assessment deferred (see --json)")
    if "effects_json" in r:
        print(f"\n   Saved JSON report: {r['effects_json']}")
    print(f"\n   {r['local_first']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
