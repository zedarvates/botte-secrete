"""CLI for skill_finder — stdlib argparse.

    python -m skills.skill_finder.cli "optimize slow postgres queries"
    python -m skills.skill_finder.cli "set up an A/B test" --local
    python -m skills.skill_finder.cli "audit dead code" --roots ~/.claude/skills --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.skill_finder.finder import find


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
    p = argparse.ArgumentParser(prog="skill_finder", description=__doc__)
    p.add_argument("query")
    p.add_argument("--roots", nargs="*", help="skill dirs to search (default: repo skills/)")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--local", action="store_true", help="local-LLM rerank (0 cloud tokens)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    roots = [Path(r).expanduser() for r in args.roots] if args.roots else None
    res = find(args.query, roots=roots, top_k=args.top, use_local=args.local)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"🔎 \"{res['query']}\"  ({res['tier']}, cloud tokens: {res['cloud_tokens']}, "
          f"catalog: {res['catalog_size']})")
    if not res["matches"]:
        print("   no matching skills")
        return 1
    for m in res["matches"]:
        print(f"   {m['score']:.2f}  {m['name']:20s} — {m['description'][:80]}")
        print(f"        ↳ {m['why']}  ({m['path']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
