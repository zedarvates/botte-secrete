"""CLI for the Conductor.

    python -m skills.conductor.cli "<goal>" [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.conductor import plan, run_goal


def _run_execute(args) -> int:
    r = run_goal(args.goal, confirm=args.confirm, dry_run=args.dry_run,
                 timeout=args.timeout)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    c = r["summary"]
    print(f"🎬 Executed plan for: {r['goal']}")
    print(f"   mode: {r['mode']}  ·  ran {c['ran']} · blocked {c['blocked']} · "
          f"skipped {c['skipped']} · failed {c['failed']}\n")
    icon = {"ran": "✅", "failed": "❌", "blocked": "🔒", "skipped": "⏭️"}
    for s in r["results"]:
        print(f"   {icon.get(s['status'], '•')} {s['capability']:18} [{s['status']}] "
              f"{s['command']}")
        print(f"        {s['note']}")
    # a failed step is a non-zero exit so callers/CI can react
    return 1 if c["failed"] else 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="conductor", description=__doc__)
    p.add_argument("goal")
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped plan under ./.botte/reports/")
    p.add_argument("--execute", action="store_true",
                   help="run the plan's read-only steps (mutating/cloud steps are gated)")
    p.add_argument("--confirm", action="store_true",
                   help="with --execute, also run the gated (mutating/cloud) steps")
    p.add_argument("--dry-run", action="store_true",
                   help="with --execute, classify every step but run nothing")
    p.add_argument("--timeout", type=int, default=120,
                   help="per-step timeout in seconds (default 120)")
    args = p.parse_args(argv)

    if args.execute:
        return _run_execute(args)

    r = plan(args.goal)
    if args.save and "error" not in r:
        from pathlib import Path as _P
        from skills.report import save
        save("plan", r, fmt=args.save, out_dir=_P(".botte") / "reports",
             title=f"Plan — {r['goal']}")
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
    print(f"\n   {r['local_first']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
