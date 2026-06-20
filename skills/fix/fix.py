"""fix — list the correctable issues in a project, each with a cost estimate.

Plan-only by design: it never edits code automatically (auto-fixers have burned
this repo before). It enumerates genuine fixes — confirmed dead code, duplication,
stale directive references — and attaches `tokens · model · money · time` to each
(via cost_estimator) plus a total, so you can decide what's worth doing.

Pure stdlib for the directive checks; the code checks reuse fallow_like (which
needs tree-sitter). Guards degrade gracefully.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from skills.cost_estimator import estimate_fix


def _code_fixes(project: Path) -> list[dict]:
    """Confirmed dead code + duplication (needs fallow_like / tree-sitter)."""
    try:
        from skills.fallow_like.scanner import ProjectScanner
        from skills.fallow_like.analyzers.dead_code import DeadCodeAnalyzer
        from skills.fallow_like.analyzers.duplication import DuplicationAnalyzer
    except Exception:
        return []
    try:
        scan = ProjectScanner(str(project)).scan()
    except Exception:
        return []
    fixes = []
    for f in DeadCodeAnalyzer().analyze(scan):
        if getattr(f, "confidence", 0) >= 0.85:   # genuine only
            fixes.append({"kind": "dead_code", "where": f"{f.file}:{f.line}",
                          "what": f"remove unused {f.symbol_type} '{f.symbol_name}'",
                          "auto": "safe-with-review"})
    for f in DuplicationAnalyzer().analyze(scan):
        loc = getattr(f, "file", "") or ""
        fixes.append({"kind": "duplication", "where": str(loc),
                      "what": "factor out duplicated block", "auto": "manual"})
    return fixes


def _directive_fixes(project: Path) -> list[dict]:
    try:
        from skills.directives_audit import audit
    except Exception:
        return []
    rep = audit(project)
    out = []
    for fnd in rep.get("findings", []):
        msg = fnd.get("message", "")
        if "not found" in msg:
            out.append({"kind": "stale_ref", "where": fnd.get("path", ""),
                        "what": msg, "auto": "manual"})
        elif "large" in msg or "tok" in msg:
            out.append({"kind": "directive", "where": fnd.get("path", ""),
                        "what": msg, "auto": "manual"})
    return out


def _totals(by_kind: dict, strategy: str) -> dict:
    tok = usd = s = 0.0
    for kind, n in by_kind.items():
        d = estimate_fix(kind, count=n, strategy=strategy).to_dict()
        tok += d["tokens_in"] + d["tokens_out"]; usd += d["usd"]; s += d["seconds"]
    return {"strategy": strategy, "tokens": int(tok), "usd": round(usd, 4),
            "seconds": round(s, 1)}


def find_fixes(project: str | Path, *, strategy: str = "recommended") -> dict:
    """Enumerate correctable issues with per-fix cost + a strategy comparison.

    strategy picks the model tier: recommended · cheapest · fastest · best — so a
    user or orchestrator can choose the methodology for the corrections.
    """
    from skills.cost_estimator.cost_estimator import STRATEGIES
    project = Path(project).resolve()
    fixes = _code_fixes(project) + _directive_fixes(project)

    by_kind: dict[str, int] = {}
    for f in fixes:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    cost_by_kind = {}
    for kind, n in by_kind.items():
        est = estimate_fix(kind, count=n, strategy=strategy)
        cost_by_kind[kind] = {"count": n, **est.to_dict(),
                              "human_each": estimate_fix(kind, strategy=strategy).human()}

    # comparison so the caller can pick a methodology
    comparison = {s: _totals(by_kind, s) for s in STRATEGIES}
    rec = comparison["recommended"]

    return {
        "project": str(project),
        "mode": "plan (dry-run — no files changed)",
        "total_fixes": len(fixes),
        "by_kind": by_kind,
        "strategy": strategy,
        "cost_by_kind": cost_by_kind,
        "totals": {"tokens": comparison[strategy]["tokens"],
                   "usd": comparison[strategy]["usd"],
                   "seconds": comparison[strategy]["seconds"],
                   "note": f"to apply ALL under the '{strategy}' strategy"},
        "strategy_comparison": comparison,
        "advice": ("cheapest = local/free (slower); fastest = lowest wall-time; "
                   "best = cloud quality; recommended = balanced "
                   f"({rec['tokens']} tok · ${rec['usd']} · ~{rec['seconds']:.0f}s)"),
        "fixes": fixes[:50],
    }
