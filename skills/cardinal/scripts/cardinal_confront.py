#!/usr/bin/env python3
"""Cardinal Confrontation Script — Blue Team vs Red Team."""

import sys
import json
from pathlib import Path
from datetime import datetime


def _load_report(path):
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: missing, unreadable or invalid JSON") from exc
    if not isinstance(report, dict) or not report:
        raise ValueError(f"{path}: expected a non-empty report object")
    return report


def _findings(report, name, alias=None):
    keys = [key for key in (name, alias) if key is not None and key in report]
    if not keys:
        raise ValueError(f"Missing findings field: {name}")
    values = [report[key] for key in keys]
    if any(not isinstance(value, list) or
           any(not isinstance(item, dict) for item in value) for value in values):
        raise ValueError(f"{name}: expected a list of finding objects")
    if any(value != values[0] for value in values[1:]):
        raise ValueError(f"Conflicting findings fields: {name} and {alias}")
    return values[0]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("Usage: cardinal_confront.py <blue_reports_dir> <red_reports_dir>")
        return 1

    blue_dir = Path(args[0])
    red_dir = Path(args[1])

    print("👑 Le Cardinal — Confrontation Bleu vs Rouge")
    print("=" * 60)

    # Missing evidence must not look like a clean review. Blue inputs are
    # checked for presence/shape; this script does not independently audit them.
    try:
        for relative in ("audit/audit-report.json", "fix-report.json",
                         "optimize/optimization-plan.json"):
            _load_report(blue_dir / relative)
        red_audit = _load_report(red_dir / "counter-audit.json")
        red_fix = _load_report(red_dir / "counter-fix.json")
        red_opt = _load_report(red_dir / "counter-optim.json")
        rochefort_fn = _findings(red_audit, "false_negatives")
        rochefort_under = _findings(red_audit, "underestimated")
        milady_regressions = _findings(red_fix, "regressions")
        milady_incomplete = _findings(red_fix, "incomplete_fixes", "incomplete")
        wardes_over = _findings(red_opt, "over_optimizations")
        wardes_skills = _findings(red_opt, "wrongly_excluded_skills", "wrongly_excluded")
    except ValueError as exc:
        print(f"Confrontation incomplete: {exc}", file=sys.stderr)
        return 2

    # Calculate blue team trust score
    blue_score = 100
    red_findings = 0

    # Rochefort vs Porthos
    red_findings += len(rochefort_fn) + len(rochefort_under)
    blue_score -= len(rochefort_fn) * 5  # -5 per false negative
    blue_score -= len(rochefort_under) * 3  # -3 per underestimated

    # Milady vs d'Artagnan
    red_findings += len(milady_regressions) + len(milady_incomplete)
    blue_score -= len(milady_regressions) * 10  # -10 per regression (serious!)
    blue_score -= len(milady_incomplete) * 3

    # Comte de Wardes vs Aramis
    red_findings += len(wardes_over) + len(wardes_skills)
    blue_score -= len(wardes_over) * 5
    blue_score -= len(wardes_skills) * 3

    blue_score = max(0, min(100, blue_score))

    # Verdict
    if blue_score >= 80:
        verdict = "FIABLE"
        verdict_color = "🟢"
    elif blue_score >= 50:
        verdict = "PARTIELLEMENT FIABLE"
        verdict_color = "🟡"
    else:
        verdict = "NON FIABLE"
        verdict_color = "🔴"

    # Print confrontation
    print(f"\n📊 Score de Confiance Équipe Bleue : {blue_score}/100 {verdict_color} {verdict}")
    print(f"   Red Team a trouvé {red_findings} problèmes")

    print(f"\n🗡️ Rochefort vs Porthos:")
    print(f"   Faux négatifs : {len(rochefort_fn)}")
    print(f"   Findings sous-estimés : {len(rochefort_under)}")
    if rochefort_fn:
        for fn in rochefort_fn[:5]:
            print(f"     • {fn.get('file', fn.get('f', '?'))}:{fn.get('line', '?')} — {str(fn.get('description', fn.get('d', '?')))[:80]}")

    print(f"\n🔪 Milady vs d'Artagnan:")
    print(f"   Régressions : {len(milady_regressions)}")
    print(f"   Fixes incomplets : {len(milady_incomplete)}")
    if milady_regressions:
        for reg in milady_regressions[:5]:
            print(f"     • {reg.get('file', reg.get('f', '?'))}:{reg.get('line', '?')} — {str(reg.get('description', reg.get('broke', '?')))[:80]}")

    print(f"\n🕯️ Comte de Wardes vs Aramis:")
    print(f"   Sur-optimisations : {len(wardes_over)}")
    print(f"   Skills mal exclus : {len(wardes_skills)}")
    if wardes_skills:
        for s in wardes_skills[:5]:
            print(f"     • {s.get('skill', '?')} — {str(s.get('reason', '?'))[:80]}")

    # Save confrontation report
    confrontation = {
        "date": datetime.now().isoformat(),
        "blue_score": blue_score,
        "verdict": verdict,
        "red_findings": red_findings,
        "rochefort": {
            "false_negatives": len(rochefort_fn),
            "underestimated": len(rochefort_under),
        },
        "milady": {
            "regressions": len(milady_regressions),
            "incomplete_fixes": len(milady_incomplete),
        },
        "conte_de_wardes": {
            "over_optimizations": len(wardes_over),
            "wrongly_excluded_skills": len(wardes_skills),
        },
    }

    output_path = red_dir / "confrontation.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(confrontation, f, indent=2, default=str)

    print(f"\n✅ Confrontation report: {output_path}")
    print(f"\n👑 Verdict du Cardinal : Équipe Bleue est {verdict}")
    return 0


if __name__ == "__main__":
    import sys as _sys  # ensure UTF-8 console on Windows (cp1252 crashes on emoji)
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass
    raise SystemExit(main())
