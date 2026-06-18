"""CLI for auto_router — stdlib argparse.

    python -m skills.auto_router.cli route "design a distributed cache"
    python -m skills.auto_router.cli run   "classify: bug or feature?"
    python -m skills.auto_router.cli providers
    python -m skills.auto_router.cli fusion cascade "is 17 prime?"
    python -m skills.auto_router.cli fusion draft  "explain the CAP theorem"
    python -m skills.auto_router.cli fusion vote   "capital of France in one word?"
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.auto_router import auto_route, auto_run, providers, fusion


def _utf8():
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None) -> int:
    _utf8()
    p = argparse.ArgumentParser(prog="auto_router", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("route", help="decide backend (no call)")
    s.add_argument("prompt"); s.add_argument("--task-type", default="")

    s = sub.add_parser("run", help="decide + execute")
    s.add_argument("prompt"); s.add_argument("--task-type", default="")
    s.add_argument("--max-tokens", type=int, default=512)

    sub.add_parser("providers", help="list cloud models + availability")

    s = sub.add_parser("fusion", help="ensemble strategies")
    s.add_argument("strategy", choices=["cascade", "draft", "vote"])
    s.add_argument("prompt"); s.add_argument("--max-tokens", type=int, default=256)

    args = p.parse_args(argv)

    if args.cmd == "route":
        print(json.dumps(auto_route(args.prompt, args.task_type), ensure_ascii=False, indent=2))
    elif args.cmd == "run":
        print(json.dumps(auto_run(args.prompt, task_type=args.task_type,
                                  max_tokens=args.max_tokens), ensure_ascii=False, indent=2))
    elif args.cmd == "providers":
        print(json.dumps(providers.catalog_overview(), ensure_ascii=False, indent=2))
    elif args.cmd == "fusion":
        fn = {"cascade": fusion.cascade, "draft": fusion.draft_refine, "vote": fusion.vote}[args.strategy]
        kw = {"max_tokens": args.max_tokens}
        print(json.dumps(fn(args.prompt, **kw), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
