"""/checkup — the canonical, already-optimal project checkup.

So you never have to hand-write a good checkup prompt: one command runs the
standard sequence in the right order and prints a single verdict.

    python -m skills.checkup.cli [<project>] [--json]

Sequence (cheap → deeper, all local / 0 cloud tokens):
    1. policy        ensure .botte/policy.md exists (the shared rules)
    2. directives    CLAUDE.md/AGENTS.md health + stale refs
    3. metrics       LOC per component + always-on cost + savings framing
    4. infra         hardware/software/MCP cluster tips
    5. duplication   stdlib AST duplicate-function scan
    6. drift         is the MCP wired? are directives stale/oversized?
Then points at the deep code audit (secrets/dead-code) for when you want it.
"""

from __future__ import annotations

import argparse
import json
import sys
from skills.console_utf8 import force_utf8
from pathlib import Path



def run(project: Path) -> dict:
    project = Path(project).resolve()
    out: dict = {"project": str(project), "drift": []}

    # 1. policy present?
    from skills.preflight import policy
    out["policy_committed"] = policy.policy_path(project).exists()
    if not out["policy_committed"]:
        out["drift"].append("No .botte/policy.md — run the deployer to commit shared rules.")

    # 2-5. reuse the auto audit (directives + infra + duplication) and metrics.
    from skills.infra_advisor import auto_audit
    aa = auto_audit(str(project))
    out["headline"] = aa["headline"]
    out["directives"] = aa.get("directives", {})
    out["infra_tips"] = aa.get("infra_tips", [])
    out["duplication"] = aa.get("duplication", {})
    out["diagram"] = aa.get("diagram", "")

    from skills.metrics import collect
    m = collect(project)
    out["loc_total"] = m.loc_total
    out["by_component"] = m.by_component
    out["cost"] = m.cost

    # 6. drift checks
    d = out["directives"]
    if isinstance(d, dict):
        if d.get("score", 100) < 90:
            out["drift"].append(f"Directives health {d.get('score')}/100 — stale/oversized; fix CLAUDE.md/AGENTS.md.")
    if any("Wire the MCP" in t.get("title", "") for t in out["infra_tips"]):
        out["drift"].append("MCP not wired here — run `python -m skills.bootstrap.cli .`")
    if m.always_on_tokens > 2000:
        out["drift"].append(f"CLAUDE.md ~{m.always_on_tokens} tok (>2000) — trims save tokens every turn.")

    out["deep_audit_hint"] = ("For secrets/dead-code: PYTHONPATH=. python "
                              "skills/mousquetaires/scripts/porthos_audit.py <project> <out>")
    return out


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="checkup", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under <project>/.botte/reports/")
    args = p.parse_args(argv)

    r = run(Path(args.project))
    if args.save:
        from skills.report import save
        paths = save("checkup", r, fmt=args.save,
                     out_dir=Path(r["project"]) / ".botte" / "reports",
                     title=f"Checkup — {r['project']}")
        r["saved_report"] = paths
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    print(f"🩺 Checkup — {r['project']}")
    print(f"   {r['headline']}  ·  {r['loc_total']:,} LOC  ·  "
          f"policy {'✓' if r['policy_committed'] else '✗ (not committed)'}")
    print(f"\n   💰 analysis cost: {r['cost']['analysis_llm_tokens']} LLM tokens · "
          f"always-on: {r['cost']['always_on_tokens_per_session']:,} tok/session")
    if r["drift"]:
        print("\n   ⚠️  Drift to fix:")
        for x in r["drift"]:
            print(f"     • {x}")
    else:
        print("\n   ✅ No drift.")
    print(f"\n   🔬 {r['deep_audit_hint']}")
    if r.get("saved_report"):
        print("\n   💾 Saved: " + " · ".join(r["saved_report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
