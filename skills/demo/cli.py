"""CLI for demo mode.

    python -m skills.demo.cli scripted [--speed 0.6] [--no-clear]
    python -m skills.demo.cli live <project> [--interval 0.5]
    python -m skills.demo.cli replay <events.json> [--speed 0.3]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.demo.demo import run_scripted, run_live, run_replay


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="demo", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scripted", help="built-in scenario — no LLM, no network")
    s.add_argument("--speed", type=float, default=0.6, help="seconds between steps")
    s.add_argument("--no-clear", action="store_true")

    s = sub.add_parser("live", help="tail a real project's event log")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--interval", type=float, default=0.5)
    s.add_argument("--no-clear", action="store_true")

    s = sub.add_parser("replay", help="replay a captured event list (JSON array)")
    s.add_argument("events_file")
    s.add_argument("--speed", type=float, default=0.3)
    s.add_argument("--no-clear", action="store_true")

    args = p.parse_args(argv)

    try:
        if args.cmd == "scripted":
            for frame in run_scripted(delay=args.speed, clear=not args.no_clear):
                print(frame)
            return 0
        if args.cmd == "live":
            print(f"watching {args.project}/.botte/events.jsonl — Ctrl+C to stop")
            for frame in run_live(args.project, poll_interval=args.interval,
                                  clear=not args.no_clear):
                print(frame)
            return 0
        events = json.loads(open(args.events_file, encoding="utf-8").read())
        for frame in run_replay(events, delay=args.speed, clear=not args.no_clear):
            print(frame)
        return 0
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
