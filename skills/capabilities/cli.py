"""CLI for the capability registry / curator.

    python -m skills.capabilities.cli map               # ASCII layered system tree
    python -m skills.capabilities.cli list [--json]     # the registry
    python -m skills.capabilities.cli curate "<goal>"   # capabilities for a goal
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.capabilities import load, ascii_map, curate


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="capabilities", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map", help="ASCII layered system tree")
    s = sub.add_parser("list", help="the capability registry")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("curate", help="capabilities relevant to a goal")
    s.add_argument("goal")
    args = p.parse_args(argv)

    if args.cmd == "map":
        print(ascii_map())
    elif args.cmd == "list":
        caps = load()
        if args.json:
            print(json.dumps([c.to_dict() for c in caps], ensure_ascii=False, indent=2))
        else:
            for c in caps:
                print(f"  [{c.layer:8}] {c.name:24} {c.description[:64]}")
    else:
        for c in curate(args.goal):
            print(f"  {c['score']:.2f} [{c['layer']:8}] {c['name']:20} — {c['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
