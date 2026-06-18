#!/usr/bin/env python3
"""Cardinal Confrontation Script — Blue Team vs Red Team."""

import sys
import json
from pathlib import Path
from datetime import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: cardinal_confront.py <blue_reports_dir> <red_reports_dir>")
        sys.exit(1)

    blue_dir = Path(sys.argv[1])
    red_dir = Path(sys.argv[2])

    print("👑 Le Cardinal — Confrontation Bleu vs Rouge")
    print("=" * 60)

    # Load blue reports
    blue_audit = json.loads((blue_dir / "audit" / "audit-report.json").read_text(encoding="utf-8")) if (blue_dir / "audit" / "audit-report.json").exists() else {}
    blue_fix = json.loads((blue_dir / "fix-report.json").read_text(encoding="utf-8")) if (blue_dir / "fix-report.json").exists() else {}
    blue_opt = json.loads((blue_dir / "optimize" / "optimization-plan.json").read_text(encoding="utf-8")) if (blue_dir / "optimize" / "optimization-plan.json").exists() else {}

    # Load red reports
    red_audit = json.loads((red_dir / "counter-audit.json").read_text(encoding="utf-8")) if (red_dir / "counter-audit.json").exists() else {}
    red_fix = json.loads((red_dir / "counter-fix.json").read_text(encoding="utf-8")) if (red_dir / "counter-fix.json").exists() else {}
    red_opt = json.loads((red_dir / "counter-optim.json").read_text(encoding="utf-8")) if (red_dir / "counter-optim.json").exists() else {}

    # Calculate blue team trust score
    blue_score = 100
    red_findings = 0

    # Rochefort vs Porthos
    rochefort_fn = red_audit.get("false_negatives", [])
    rochefort_under = red_audit.get("underestimated", [])
    red_findings += len(rochefort_fn) + len(rochefort_under)
    blue_score -= len(rochefort_fn) * 5  # -5 per false negative
    blue_score -= len(rochefort_under) * 3  # -3 per underestimated

    # Milady vs d'Artagnan
    milady_regressions = red_fix.get("regressions", [])
    milady_incomplete = red_fix.get("incomplete_fixes", [])
    red_findings += len(milady_regressions) + len(milady_incomplete)
    blue_score -= len(milady_regressions) * 10  # -10 per regression (serious!)
    blue_score -= len(milady_incomplete) * 3

    # Comte de Wardes vs Aramis
    wardes_over = red_opt.get("over_optimizations", [])
    wardes_skills = red_opt.get("wrongly_excluded_skills", [])
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
            print(f"     • {fn.get('file', '?')}:{fn.get('line', '?')} — {fn.get('description', '?')[:80]}")

    print(f"\n🔪 Milady vs d'Artagnan:")
    print(f"   Régressions : {len(milady_regressions)}")
    print(f"   Fixes incomplets : {len(milady_incomplete)}")
    if milady_regressions:
        for reg in milady_regressions[:5]:
            print(f"     • {reg.get('file', '?')}:{reg.get('line', '?')} — {reg.get('description', '?')[:80]}")

    print(f"\n🕯️ Comte de Wardes vs Aramis:")
    print(f"   Sur-optimisations : {len(wardes_over)}")
    print(f"   Skills mal exclus : {len(wardes_skills)}")
    if wardes_skills:
        for s in wardes_skills[:5]:
            print(f"     • {s.get('skill', '?')} — {s.get('reason', '?')[:80]}")

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


if __name__ == "__main__":
    import sys as _sys  # ensure UTF-8 console on Windows (cp1252 crashes on emoji)
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass
    main()
