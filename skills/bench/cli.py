"""CLI for botte bench.

    python -m skills.bench.cli            # table + totals
    python -m skills.bench.cli --json
    python -m skills.bench.cli --save md
"""

from __future__ import annotations

import argparse
import json

from skills.console_utf8 import force_utf8
from skills.bench.bench import run


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="bench", description=__doc__)
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under .botte/reports/")
    args = p.parse_args(argv)

    r = run()
    if args.save:
        from skills.report import save
        r["saved_report"] = save("bench", r, fmt=args.save,
                                 title="Botte bench — routing savings, reproducible")

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    t = r["totals"]
    print(f"🧪 botte bench — {r['corpus_size']} tasks, {r['local_pct']}% stayed local")
    print(f"   baseline: {r['baseline']}")
    print()
    print(f"{'task':<45} {'decision':<8} {'tier':<9} {'tokens':>8}  vs baseline")
    for row in r["rows"]:
        print(f"{row['task']:<45} {row['decision']:<8} {row['tier']:<9} "
              f"{row['actual_tokens']:>8}  ({row['baseline_tokens']})")
    print()
    print(f"   with belt : {t['with_belt_tokens']:>8,} tok  ${t['with_belt_usd']:.4f}")
    print(f"   baseline  : {t['baseline_tokens']:>8,} tok  ${t['baseline_usd']:.4f}")
    print(f"   savings   : {t['token_savings_pct']:>7}% tokens  ·  "
          f"{t['usd_savings_pct']:>7}% cost")
    if r.get("saved_report"):
        print("\n   💾 Saved: " + " · ".join(r["saved_report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
