"""CLI for context_profiler — always-on prefix vs a small model's window.

    python -m skills.context_profiler.cli [<project>] [--json]
"""

from __future__ import annotations

import argparse
import json

from skills.console_utf8 import force_utf8
from skills.context_profiler import profile


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="context_profiler", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    r = profile(args.project)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    c = r["components"]
    print(f"🧮 Context prefix — {r['project']}")
    print(f"   {r['counts']['tools']} MCP tools · {r['counts']['skills']} skills\n")
    for name in ("directives", "core_agent", "tool_schemas", "skill_catalog"):
        print(f"   {name:14} {c.get(name, 0):>6} tok")
    print(f"   {'TOTAL':14} {r['total_prefix_tokens']:>6} tok  →  "
          + " · ".join(f"{k} {v}%" for k, v in r["window_pct"].items()))
    print(f"\n   ✂️  reducible: {r['reducible_tokens']} tok → minimal prefix "
          f"{r['minimal_prefix_tokens']} tok ("
          + " · ".join(f"{k} {v}%" for k, v in r["minimal_window_pct"].items()) + ")")
    for pl in r["reduction_plan"]:
        print(f"     • {pl['lever']}: −{pl['saves_tokens']} tok — {pl['how']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
