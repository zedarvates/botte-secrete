"""CLI for context_profiler — always-on prefix vs a small model's window.

    python -m skills.context_profiler.cli [<project>] [--json] [--host]
"""

from __future__ import annotations

import argparse
import json

from skills.console_utf8 import force_utf8
from skills.context_profiler import profile, profile_host


def _print_profile(r: dict) -> None:
    """Shared printer for both modes."""
    c = r["components"]
    bd = r.get("breakdown")

    print(f"🧮 Context prefix — {r['project']}")
    if bd:
        print(f"   {r['counts'].get('tools', 0)} MCP tools · "
              f"{r['counts'].get('skills', 0)} project skills · "
              f"{r['counts'].get('host_skills', 0)} host skills")
        print(f"\n   ── Project (botte controls) ──")
        for name in ("directives", "core_agent", "tool_schemas", "skill_catalog"):
            if name in c:
                print(f"   {name:18} {c.get(name, 0):>6} tok")
        proj_sub = "→ project subtotal"
        print(f"   {proj_sub:18} {bd['project']:>6} tok")
        print(f"\n   ── Host (runtime imposes) ──")
        for name in ("system_reminder", "memory_block", "user_profile",
                      "host_skill_catalog", "mcp_servers"):
            if name in c:
                print(f"   {name:18} {c.get(name, 0):>6} tok")
        host_sub = "→ host subtotal"
        print(f"   {host_sub:18} {bd['host']:>6} tok")
        print(f"\n   ⚖️  {bd['project_pct']}% project · {bd['host_pct']}% host")
    else:
        print(f"   {r['counts']['tools']} MCP tools · {r['counts']['skills']} skills\n")
        for name in ("directives", "core_agent", "tool_schemas", "skill_catalog"):
            print(f"   {name:14} {c.get(name, 0):>6} tok")

    total_label = "TOTAL    " if bd else "TOTAL"
    print(f"   {total_label} {r['total_prefix_tokens']:>6} tok  →  "
          + " · ".join(f"{k} {v}%" for k, v in r["window_pct"].items()))

    if r["reduction_plan"]:
        print(f"\n   ✂️  reducible: {r['reducible_tokens']} tok → minimal prefix "
              f"{r['minimal_prefix_tokens']} tok ("
              + " · ".join(f"{k} {v}%" for k, v in r["minimal_window_pct"].items()) + ")")
        for pl in r["reduction_plan"]:
            print(f"     • {pl['lever']}: −{pl['saves_tokens']} tok — {pl['how']}")
    else:
        print("\n   ✅ No reduction levers identified")


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="context_profiler", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--host", action="store_true",
                   help="Include host-level prefix estimation (system-reminder, "
                        "memory, user profile, host skill catalog, MCP server descriptions)")
    args = p.parse_args(argv)

    if args.host:
        r = profile_host(args.project)
    else:
        r = profile(args.project)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    _print_profile(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
