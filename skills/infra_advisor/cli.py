"""CLI for infra_advisor.

    python -m skills.infra_advisor.cli tips [--subnet] [--json]
    python -m skills.infra_advisor.cli auto [<project>] [--subnet] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from skills.console_utf8 import force_utf8
from pathlib import Path

from skills.infra_advisor.advisor import advise
from skills.infra_advisor.auto_audit import auto_audit



_ICON = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🔵"}


def _print_tips(tips):
    for t in tips:
        print(f"   {_ICON.get(t['priority'],'•')} [{t['priority']}] {t['category']:8s} {t['title']}")
        print(f"        why: {t['why']}")
        print(f"        ⇒   {t['impact']}")


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="infra_advisor", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("tips", help="hardware/software/MCP tips + ASCII diagram")
    s.add_argument("--subnet", action="store_true")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("auto", help="one-pass audit on the project (directives+infra+dups)")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--subnet", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under <project>/.botte/reports/")

    args = p.parse_args(argv)

    if args.cmd == "tips":
        rep = advise(scan_subnet=args.subnet, fresh=True)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2)); return 0
        print(rep["diagram"])
        print(f"\n🛠️  Infra score: {rep['infra_score']}/100 — {len(rep['tips'])} tip(s):")
        _print_tips(rep["tips"])
        return 0

    rep = auto_audit(args.project, scan_subnet=args.subnet)
    if getattr(args, "save", None):
        from skills.report import save
        from pathlib import Path as _P
        paths = save("audit", rep, fmt=args.save,
                     out_dir=_P(rep["project"]) / ".botte" / "reports",
                     title=f"Auto audit — {rep['project']}")
        rep["saved_report"] = paths
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2)); return 0
    print(f"🧦 Auto audit — {rep['project']}")
    print(f"   {rep['headline']}\n")
    print(rep["diagram"])
    print(f"\n🛠️  Infra tips ({len(rep['infra_tips'])}):")
    _print_tips(rep["infra_tips"])
    dup = rep.get("duplication", {})
    if dup.get("duplicates"):
        print(f"\n♻️  Duplicate function groups ({dup['duplicate_groups']}):")
        for d in dup["duplicates"][:8]:
            print(f"     ×{d['count']}  " + " | ".join(d["locations"][:3]))
    print("\n🔎 Deeper passes:")
    for s in rep["deeper_passes"]:
        print(f"     • {s}")
    if rep.get("saved_report"):
        print("\n💾 Saved: " + " · ".join(rep["saved_report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
