"""CLI for fix — list correctable issues with cost estimates (plan-only).

    python -m skills.fix.cli [<project>] [--json] [--save md|html|both]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.fix import find_fixes


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="fix", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--strategy", default="recommended",
                   choices=["recommended", "cheapest", "fastest", "best"],
                   help="correction methodology to cost")
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"])
    args = p.parse_args(argv)

    r = find_fixes(args.project, strategy=args.strategy)
    if args.save:
        from skills.report import save
        save("fixes", r, fmt=args.save, out_dir=Path(r["project"]) / ".botte" / "reports",
             title=f"Fix plan — {r['project']}")
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0

    print(f"🩹 Fix plan — {r['project']}  ({r['mode']})")
    print(f"   {r['total_fixes']} correctable issue(s): {r['by_kind']}\n")
    print("   Cost to apply, by kind (tokens · model · money · time):")
    for kind, c in r["cost_by_kind"].items():
        print(f"     {kind:12} ×{c['count']:<3} → {c['tokens_in']+c['tokens_out']:>5} tok · "
              f"{c['model_class'][:22]:22} · ${c['usd']:.4f} · ~{c['seconds']:.0f}s")
    print("\n   Choose a methodology (tokens · money · time):")
    for s, c in r["strategy_comparison"].items():
        mark = " ←" if s == r["strategy"] else ""
        print(f"     {s:12} {c['tokens']:>6,} tok · ${c['usd']:.4f} · ~{c['seconds']:.0f}s{mark}")
    print(f"\n   💡 {r['advice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
