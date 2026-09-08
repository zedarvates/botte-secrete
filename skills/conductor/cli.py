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
    if args.effects:
        from skills.atomic_json import write_json
        directory = Path(".botte") / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        prefix = Path(timestamped_name(f"{kind}-effects", "json")).stem + "-"
        fd, name = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=directory)
        os.close(fd)
        target = Path(name)
        report["effects_json"] = target.as_posix()
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
                 observe_effects=args.observe_effects)
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
                  f"{e['unfinished_calls']} unfinished calls; coverage partial (see --json)")
    if "effects_json" in r:
        print(f"   Complete effects report: {r['effects_json']}")
    # a failed step is a non-zero exit so callers/CI can react
    return 1 if c["failed"] else 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="conductor", description=__doc__)
    p.add_argument("goal")
    p.add_argument("--json", action="store_true")
    p.add_argument("--effects", action="store_true",
                   help="include selected capabilities' effects declarations; no extra authority")
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
    p.add_argument("--timeout", type=int, default=120,
                   help="per-step timeout in seconds (default 120)")
    args = p.parse_args(argv)
    if args.observe_effects:
        if not args.execute:
            p.error("--observe-effects requires --execute")
        args.effects = True

    if args.execute:
        return _run_execute(args)

    r = plan(args.goal, include_effects=args.effects)
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
    if "effects_json" in r:
        print(f"\n   Complete effects report: {r['effects_json']}")
    print(f"\n   {r['local_first']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
