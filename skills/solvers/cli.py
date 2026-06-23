"""CLI for solvers — assignment / bin-packing / precedence scheduling (0 tokens).

    python -m skills.solvers.cli assign w1,w2,w3 a:5 b:3 c:8 d:2
    python -m skills.solvers.cli pack 10 a:4 b:7 c:3 d:6
    python -m skills.solvers.cli schedule build test:build deploy:test,build
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.solvers import assign_balanced, bin_pack, schedule


def _pairs(specs, default=1.0):
    out = []
    for s in specs:
        if ":" in s:
            name, val = s.rsplit(":", 1)
            out.append((name, float(val)))
        else:
            out.append((s, default))
    return out


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="solvers", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("assign", help="balance (name:cost) tasks across workers")
    a.add_argument("workers", help="comma-separated worker names")
    a.add_argument("tasks", nargs="+", help="name:cost …")

    b = sub.add_parser("pack", help="pack (name:size) items into bins of capacity")
    b.add_argument("capacity", type=float)
    b.add_argument("items", nargs="+", help="name:size …")

    s = sub.add_parser("schedule", help="order steps under deps (step:pre1,pre2)")
    s.add_argument("steps", nargs="+", help="step or step:pre1,pre2 …")

    args = p.parse_args(argv)

    if args.cmd == "assign":
        r = assign_balanced(_pairs(args.tasks), args.workers.split(","))
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "pack":
        r = bin_pack(_pairs(args.items), args.capacity)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    # schedule
    steps, deps = [], {}
    for spec in args.steps:
        if ":" in spec:
            name, pres = spec.split(":", 1)
            steps.append(name)
            deps[name] = [x for x in pres.split(",") if x]
        else:
            steps.append(spec)
    r = schedule(steps, deps)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 1 if "error" in r else 0


if __name__ == "__main__":
    raise SystemExit(main())
