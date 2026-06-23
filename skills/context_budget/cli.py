"""CLI for context_budget — optimal skill set under a token budget.

    python -m skills.context_budget.cli "<task>" [--budget N] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.context_budget import select_skills


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="context_budget", description=__doc__)
    p.add_argument("query")
    p.add_argument("--budget", type=int, default=4000, help="token budget (default 4000)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    r = select_skills(args.query, budget=args.budget)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    print(f"🎒 Context budget — \"{r['query']}\"  (budget {r['budget']} tok)")
    print(f"   chosen {len(r['chosen'])} · ~{r['tokens_used']} tok used · "
          f"relevance {r['relevance_captured']}\n")
    for it in r["chosen"]:
        print(f"   ✓ {it['name']:20} ~{it['tokens']:5} tok  (rel {it['relevance']:.2f})")
    if r["dropped"]:
        print("\n   dropped (over budget):")
        for it in r["dropped"][:8]:
            print(f"   · {it['name']:20} ~{it['tokens']:5} tok  (rel {it['relevance']:.2f})")
    print(f"\n   {r['savings_note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
