"""CLI: python -m skills.dashboard.cli [<project>] [--json] [--tui] [--watch]"""
from __future__ import annotations
import argparse, json, sys, time
from skills.console_utf8 import force_utf8
from skills.dashboard.dashboard import generate, collect


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="dashboard", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--tui", action="store_true", help="render once as ANSI panels instead of HTML")
    p.add_argument("--watch", action="store_true", help="re-render the TUI every --interval seconds")
    p.add_argument("--interval", type=float, default=5.0)
    args = p.parse_args(argv)

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
