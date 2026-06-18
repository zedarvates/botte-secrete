"""CLI for project metrics.

    python -m skills.metrics.cli <project> [--json] [--porthos <audit-report.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.metrics.metrics import collect


def _utf8():
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _bar(n: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = round(width * n / total)
    return "█" * filled + "·" * (width - filled)


def main(argv=None) -> int:
    _utf8()
    p = argparse.ArgumentParser(prog="botte-metrics", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--porthos", default=None, help="path to a porthos audit-report.json")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    m = collect(args.project, porthos_report=Path(args.porthos) if args.porthos else None)
    if args.json:
        print(json.dumps(m.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"📐 Metrics — {m.project}")
    print(f"   {m.files_total} code files · {m.loc_total:,} LOC · "
          f"{m.duplicate_groups} duplicate-fn groups · directives {m.directive_score}/100")

    if m.by_component:
        print("\n   By component:")
        for comp, info in sorted(m.by_component.items(), key=lambda kv: -kv[1]["loc"])[:10]:
            langs = ", ".join(f"{k} {v:,}" for k, v in
                              sorted(info["langs"].items(), key=lambda kv: -kv[1])[:3])
            print(f"     {comp:<24.24} {info['loc']:>8,} LOC  {_bar(info['loc'], m.loc_total)}")
            print(f"       {langs}")

    if m.by_language:
        top = ", ".join(f"{k} {v:,}" for k, v in
                        sorted(m.by_language.items(), key=lambda kv: -kv[1])[:6])
        print(f"\n   Languages: {top}")

    c = m.cost
    print("\n   💰 Cost framing (estimates):")
    print(f"     analysis cost ............ {c['analysis_llm_tokens']} LLM tokens (deterministic scans)")
    print(f"     always-on context ........ {c['always_on_tokens_per_turn']:,} tok/turn "
          f"≈ {c['always_on_tokens_per_session']:,} tok/session ({c['always_on_note']})")
    print(f"     skill-search avoided ..... {c['skill_search_tokens_avoided']:,} tok ({c['skill_search_note']})")
    print(f"     local routing ............ {c['local_routing_note']}")

    if m.deep:
        h = m.deep.get("health", {})
        by = m.deep.get("by", {})
        sk = m.deep.get("skipped", [])
        print(f"\n   🔬 Deep audit: health {h.get('s','?')}/100 ({h.get('g','?')}) · "
              f"dead {by.get('dead',0)} · secrets {by.get('sec',0)}"
              + (f" · skipped {', '.join(sk)}" if sk else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
