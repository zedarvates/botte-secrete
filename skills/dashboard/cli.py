"""CLI: python -m skills.dashboard.cli [<project>] [--json] [--tui] [--watch]

Fleet (multi-project, opt-in registry at ~/.botte/fleet.json):
    python -m skills.dashboard.cli fleet add <project>
    python -m skills.dashboard.cli fleet remove <project>
    python -m skills.dashboard.cli fleet list
    python -m skills.dashboard.cli --fleet [--json]
"""
from __future__ import annotations
import argparse, json, sys, time
from skills.console_utf8 import force_utf8
from skills.dashboard.dashboard import generate, collect


def _cmd_fleet(argv) -> int:
    from skills.dashboard import fleet
    p = argparse.ArgumentParser(prog="dashboard fleet")
    sub = p.add_subparsers(dest="action", required=True)
    s = sub.add_parser("add"); s.add_argument("project")
    s = sub.add_parser("remove"); s.add_argument("project")
    sub.add_parser("list")
    args = p.parse_args(argv)

    if args.action == "add":
        projects = fleet.add(args.project)
        print(f"added. fleet now has {len(projects)} project(s).")
    elif args.action == "remove":
        projects = fleet.remove(args.project)
        print(f"removed. fleet now has {len(projects)} project(s).")
    else:
        projects = fleet.list_fleet()
        if not projects:
            print("(fleet is empty — `dashboard fleet add <project>` to register one)")
        for proj in projects:
            print(f"  {proj}")
    return 0


def main(argv=None) -> int:
    force_utf8()
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "fleet":
        return _cmd_fleet(argv[1:])

    p = argparse.ArgumentParser(prog="dashboard", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--tui", action="store_true", help="render once as ANSI panels instead of HTML")
    p.add_argument("--watch", action="store_true", help="re-render the TUI every --interval seconds")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--fleet", action="store_true",
                   help="aggregate every registered project instead of one")
    args = p.parse_args(argv)

    if args.fleet:
        from skills.dashboard import fleet
        agg = fleet.aggregate()
        if args.json:
            print(json.dumps(agg, ensure_ascii=False, indent=2))
            return 0
        t = agg["totals"]
        print(f"🧦 Fleet — {t['projects_ok']} project(s) "
              f"({t['projects_errored']} unreachable)")
        print(f"   {t['loc_total']:,} LOC total  ·  "
              f"{t['tokens_saved_total']:,} tokens saved  ·  "
              f"{t['outstanding_fixes_total']} outstanding fixes")
        for proj in agg["projects"]:
            print(f"     {proj['project']}  ·  {proj['loc']:,} LOC  ·  "
                  f"{proj['tokens_saved']:,} tok saved  ·  {proj['outstanding_fixes']} fixes")
        for err in agg["errored"]:
            print(f"     ⚠ {err['project']}  ·  {err['error']}")
        return 0

    if args.watch:
        from skills.dashboard.tui import render
        from skills.demo.render import clear_screen
        try:
            while True:
                data = collect(args.project)
                clear_screen()
                print(render(data))
                print(f"\n(refreshing every {args.interval:.0f}s — Ctrl+C to stop)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped")
        return 0

    if args.tui:
        from skills.dashboard.tui import render
        print(render(collect(args.project)))
        return 0

    if args.json:
        print(json.dumps(collect(args.project), ensure_ascii=False, indent=2)); return 0
    paths = generate(args.project, fmt="both")
    print("📊 Dashboard saved:\n   " + "\n   ".join(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
