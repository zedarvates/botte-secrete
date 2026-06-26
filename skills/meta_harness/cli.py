"""CLI for meta_harness — stdlib argparse.

    python -m skills.meta_harness.cli run . audit fix test
    python -m skills.meta_harness.cli run . full --approval
    python -m skills.meta_harness.cli plans
    python -m skills.meta_harness.cli agents
    python -m skills.meta_harness.cli status <session_name>
    python -m skills.meta_harness.cli rollback <session_name>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.meta_harness import MetaHarness


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="meta_harness", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="Run a pipeline of agents")
    s.add_argument("workdir", help="Project root", nargs="?", default=".")
    s.add_argument("agents", nargs="+", help="Agent names or built-in plan name")
    s.add_argument("--approval", action="store_true",
                   help="Require human approval before each destructive step")
    s.add_argument("--format", choices=["report", "json"], default="report")

    sub.add_parser("plans", help="List available built-in plans")
    sub.add_parser("agents", help="List available agents")

    s = sub.add_parser("status", help="Show pipeline session status")
    s.add_argument("session_name", help="Session name (from prior run)")

    s = sub.add_parser("rollback", help="Rollback a pipeline session")
    s.add_argument("session_name", help="Session to rollback")

    args = p.parse_args(argv)

    if args.cmd == "run":
        h = MetaHarness(workdir=args.workdir, approval=args.approval)
        workdir = str(Path(args.workdir).resolve())

        # Check if first arg is a built-in plan
        builtin = h.list_plans()
        if args.agents[0] in builtin:
            plan = h.plan(builtin[args.agents[0]], approval=args.approval)
        else:
            plan = h.plan(args.agents, approval=args.approval)

        print(f"📋 Plan: {plan.name}")
        print(f"   Steps: {[s.agent for s in plan.steps]}")
        print()

        session = h.execute(plan)

        if args.format == "json":
            print(session.to_json())
        else:
            print(session.report())

        sys.stdout.flush()
        return 0 if not plan.has_failed else 1

    elif args.cmd == "plans":
        h = MetaHarness()
        plans = h.list_plans()
        print("Built-in plans:")
        for name, agents in plans.items():
            print(f"  📋 {name:<15} → {' → '.join(agents)}")
        return 0

    elif args.cmd == "agents":
        h = MetaHarness()
        agents = h.list_agents()
        print("Available agents:")
        print(f"{'Name':<20} {'Skill':<20} {'Description'}")
        print("-" * 65)
        for a in agents:
            skill = a["skill"] or "(shell)"
            reqs = f"  [requires: {', '.join(a['requires'])}]" if a["requires"] else ""
            print(f"  {a['name']:<18} {skill:<18} {a['description']}{reqs}")
        return 0

    elif args.cmd == "status":
        session_path = Path(f".botte-cache/sessions/{args.session_name}.json")
        if not session_path.exists():
            print(f"❌ Session not found: {session_path}")
            return 1
        data = json.loads(session_path.read_text())
        print(json.dumps(data, indent=2))
        return 0

    elif args.cmd == "rollback":
        print("⚠️  Rollback: cleaning up sandbox directories...")
        import shutil
        sandbox_dir = Path(f".botte-sandbox/")
        if sandbox_dir.exists():
            shutil.rmtree(str(sandbox_dir))
            print(f"   Removed {sandbox_dir}")
        print("   ✅ Rollback complete")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
