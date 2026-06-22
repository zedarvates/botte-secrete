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

    # 6. security — taint / data-flow scan (0 cloud tokens, symbolic)
    out["security"] = _security_summary(project)

    # 7. drift checks
    d = out["directives"]
    if isinstance(d, dict):
        if d.get("score", 100) < 90:
            out["drift"].append(f"Directives health {d.get('score')}/100 — stale/oversized; fix CLAUDE.md/AGENTS.md.")
    if any("Wire the MCP" in t.get("title", "") for t in out["infra_tips"]):
        out["drift"].append("MCP not wired here — run `python -m skills.bootstrap.cli .`")
    if m.always_on_tokens > 2000:
        out["drift"].append(f"CLAUDE.md ~{m.always_on_tokens} tok (>2000) — trims save tokens every turn.")
    sec = out["security"]
    if sec.get("high"):
        out["drift"].append(
            f"{sec['high']} security finding(s) (taint/data-flow) — "
            "run `python -m skills.fallow_like.cli taint .`")

    out["deep_audit_hint"] = ("For secrets/dead-code: PYTHONPATH=. python "
                              "skills/mousquetaires/scripts/porthos_audit.py <project> <out>")
    return out


def _security_summary(project: Path) -> dict:
    """Run the taint/data-flow analyzer and summarise it for the checkup."""
    try:
        from skills.fallow_like.config import FallowConfig
        from skills.fallow_like.cli import run_analysis
    except ImportError:
        return {"count": 0, "high": 0, "by_cwe": {}, "top": [], "available": False}
    cfg = FallowConfig(
        project_root=project,
        enable_dead_code=False, enable_duplication=False, enable_complexity=False,
        enable_boundaries=False, enable_feature_flags=False, enable_secrets=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    findings = run_analysis(cfg).taint
    by_cwe: dict = {}
    for f in findings:
        by_cwe[f.cwe] = by_cwe.get(f.cwe, 0) + 1
    high = sum(1 for f in findings if f.severity in ("critical", "error"))
    top = [{"file": f.file, "line": f.line, "cwe": f.cwe, "message": f.message,
            "confidence": f.confidence}
           for f in sorted(findings, key=lambda x: -x.confidence)[:5]]
    return {"count": len(findings), "high": high, "by_cwe": by_cwe,
            "top": top, "available": True}


# Stable marker so a CI bot can find & update its own comment instead of spamming.
PR_COMMENT_MARKER = "<!-- botte-checkup -->"


def format_pr_comment(result: dict, *, repo: str | None = None,
                      sha: str | None = None) -> str:
    """Render a checkup result as a Markdown PR comment. Pure — no I/O.

    Verdict-first: a clear pass/drift line, the headline + key numbers, and the
    actionable drift list. Carries a stable marker so the workflow can edit its
    previous comment in place.
    """
    drift = result.get("drift", []) or []
    cost = result.get("cost", {}) or {}
    verdict = "✅ **No drift** — project is in good shape." if not drift else (
        f"⚠️ **{len(drift)} drift item{'s' if len(drift) != 1 else ''} to fix**")

    lines = [PR_COMMENT_MARKER, "## 🧦 Botte Secrète — checkup", "", verdict, ""]
    headline = result.get("headline")
    if headline:
        lines.append(f"> {headline}")
        lines.append("")

    loc = result.get("loc_total")
    policy_ok = result.get("policy_committed")
    facts = []
    if loc is not None:
        facts.append(f"**{loc:,}** LOC")
    facts.append(f"policy {'✓ committed' if policy_ok else '✗ not committed'}")
    if "analysis_llm_tokens" in cost:
        facts.append(f"analysis cost **{cost['analysis_llm_tokens']} LLM tokens**")
    if "always_on_tokens_per_session" in cost:
        facts.append(f"always-on **{cost['always_on_tokens_per_session']:,} tok/session**")
    lines.append(" · ".join(facts))
    lines.append("")

    if drift:
        lines.append("### Drift to fix")
        for x in drift:
            lines.append(f"- {x}")
        lines.append("")

    sec = result.get("security") or {}
    if sec.get("count"):
        cwes = ", ".join(f"{k}×{v}" for k, v in sorted(sec.get("by_cwe", {}).items()))
        lines.append(f"### 🛡️ Security — {sec['count']} taint candidate(s) "
                     f"({sec.get('high', 0)} high) · {cwes}")
        for t in sec.get("top", []):
            lines.append(f"- `{t['file']}:{t['line']}` [{t['cwe']}] {t['message']} "
                         f"(conf {t['confidence']})")
        lines.append("")
    elif sec.get("available"):
        lines.append("### 🛡️ Security — no taint/data-flow candidates")
        lines.append("")

    footer = "_local-first checkup · 0 cloud tokens_"
    if repo and sha:
        footer += f" · [`{sha[:7]}`](https://github.com/{repo}/commit/{sha})"
    lines.append(footer)
    return "\n".join(lines)


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="checkup", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--pr-comment", action="store_true",
                   help="print a Markdown PR comment (for the GitHub Action)")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under <project>/.botte/reports/")
    args = p.parse_args(argv)

    r = run(Path(args.project))
    if args.pr_comment:
        import os
        print(format_pr_comment(r, repo=os.environ.get("GITHUB_REPOSITORY"),
                                sha=os.environ.get("GITHUB_SHA")))
        return 0
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
    sec = r.get("security") or {}
    if sec.get("count"):
        cwes = ", ".join(f"{k}×{v}" for k, v in sorted(sec.get("by_cwe", {}).items()))
        print(f"\n   🛡️  Security: {sec['count']} taint candidate(s) "
              f"({sec.get('high', 0)} high) · {cwes}")
    elif sec.get("available"):
        print("\n   🛡️  Security: no taint/data-flow candidates")
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
