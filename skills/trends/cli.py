"""CLI for trends.

    python -m skills.trends.cli snapshot [<project>]
    python -m skills.trends.cli show [<project>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.trends import snapshot, show


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="trends", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="record current metrics")
    s.add_argument("project", nargs="?", default=".")
    s = sub.add_parser("show", help="series + delta since previous run")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "snapshot":
        print(json.dumps(snapshot(args.project), ensure_ascii=False, indent=2)); return 0

    r = show(args.project)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
    print(f"📈 Trends — {r['snapshots']} snapshot(s)")
    if r["latest"]:
        print(f"   latest: {r['latest']}")
    if r["delta_since_previous"]:
        print("   change since previous:")
        for k, d in r["delta_since_previous"].items():
            arrow = "▲" if d["change"] > 0 else ("▼" if d["change"] < 0 else "=")
            print(f"     {k:18} {d['from']} → {d['to']}  ({arrow}{abs(d['change'])})")
    else:
        print("   (need ≥2 snapshots for a delta — run `snapshot` again later)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
