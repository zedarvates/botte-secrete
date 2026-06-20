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


def find_fixes(project: str | Path) -> dict:
    """Enumerate correctable issues with per-fix and total cost estimates."""
    project = Path(project).resolve()
    fixes = _code_fixes(project) + _directive_fixes(project)

    by_kind: dict[str, int] = {}
    for f in fixes:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    # cost per fix (representative) + totals per kind
    cost_by_kind = {}
    tot_tok = tot_usd = tot_s = 0.0
    for kind, n in by_kind.items():
        est = estimate_fix(kind, count=n)
        d = est.to_dict()
        cost_by_kind[kind] = {"count": n, **d, "human_each": estimate_fix(kind).human()}
        tot_tok += d["tokens_in"] + d["tokens_out"]
        tot_usd += d["usd"]
        tot_s += d["seconds"]

    return {
        "project": str(project),
        "mode": "plan (dry-run — no files changed)",
        "total_fixes": len(fixes),
        "by_kind": by_kind,
        "cost_by_kind": cost_by_kind,
        "totals": {"tokens": int(tot_tok), "usd": round(tot_usd, 4),
                   "seconds": round(tot_s, 1),
                   "note": "estimate to apply ALL with the suggested model tiers"},
        "fixes": fixes[:50],
    }
