"""CLI for the event log.

    python -m skills.events.cli tail [project] [-n 20] [--json]
    python -m skills.events.cli log <kind> [project] --field key=value ...
    python -m skills.events.cli clear [project]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.events.events import log_event, tail_events, clear_events


def _fmt(rec: dict) -> str:
    ts = rec.get("ts", 0)
    extra = " ".join(f"{k}={v}" for k, v in rec.items() if k not in ("ts", "kind"))
    return f"[{ts:.0f}] {rec.get('kind', '?'):<9} {extra}"


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="events", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("tail", help="show the last N events")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("log", help="append one event (for scripting/testing)")
    s.add_argument("kind")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--field", action="append", default=[],
                    help="key=value, repeatable")

    s = sub.add_parser("clear", help="delete the event log")
    s.add_argument("project", nargs="?", default=".")

    args = p.parse_args(argv)

    if args.cmd == "tail":
        recs = tail_events(args.project, n=args.n)
        if args.json:
            print(json.dumps(recs, ensure_ascii=False, indent=2))
        else:
            for rec in recs:
                print(_fmt(rec))
            if not recs:
                print("(no events yet)")
        return 0

    if args.cmd == "log":
        fields = {}
        for kv in args.field:
            key, _, val = kv.partition("=")
            fields[key] = val
        log_event(args.kind, project_root=args.project, **fields)
        print(f"logged {args.kind}")
        return 0

    clear_events(args.project)
    print("event log cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
