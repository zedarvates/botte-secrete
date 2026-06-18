#!/usr/bin/env python3
"""
karpathy-review.py — Automated code review based on Karpathy's 4 principles.

Usage:
  python3 karpathy-review.py --diff /path/to/patch.patch
  python3 karpathy-review.py --git HEAD~3
  python3 karpathy-review.py --file /path/to/file.py
"""

import re, sys, json
from pathlib import Path


P1_PATTERNS = {
    "trial_and_error": re.compile(r"TODO|FIXME|HACK|XXX|workaround|temporary|quick.fix"),
    "unplanned_change": re.compile(r"just.see|let.me.try|maybe.this|random|guess"),
    "large_unexplained": lambda lines: len(lines) > 100 and not any("plan" in l.lower() or "approach" in l.lower() for l in lines if l.strip().startswith("#")),
}

P2_PATTERNS = {
    "over_abstraction": re.compile(r"Abstract\w*Factory|\w*Strategy|Abstract\w+Provider|\w*Builder"),
    "speculative": re.compile(r"for.future.use|extensibility|in.case.we|reserved.for"),
    "feature_creep": re.compile(r"also|additionally|meanwhile|besides", re.IGNORECASE),
    "deep_nesting": lambda lines: sum(1 for l in lines if l.startswith(" " * 32)) > 3,
    "magic_numbers": lambda lines: len(re.findall(r"\b\d{4,}\b", "\n".join(lines))) > 3,
}

P3_PATTERNS = {
    "mixed_format": re.compile(r"^\s*[+-].*$"),
    "whitespace_only": re.compile(r"^[+-]\s*$"),
    "comment_deletion": re.compile(r"^-#"),
}

P4_PATTERNS = {
    "no_test": lambda lines: not any("test" in l.lower() or "assert" in l.lower() for l in lines),
    "self_review": lambda lines: "looks good" in "\n".join(lines).lower() and "test" not in "\n".join(lines).lower(),
}


def review_diff(diff_text: str) -> dict:
    """Review a diff patch against Karpathy's 4 principles."""
    lines = diff_text.split("\n")
    added = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in lines if l.startswith("-") and not l.startswith("---")]

    results = {
        "P1_think_before_coding": {"score": 100, "warnings": []},
        "P2_simplicity": {"score": 100, "warnings": []},
        "P3_clean_diffs": {"score": 100, "warnings": []},
        "P4_verifiable_tests": {"score": 100, "warnings": []},
    }

    # P1: Think Before Coding
    if P1_PATTERNS["trial_and_error"].search("\n".join(added)):
        results["P1_think_before_coding"]["warnings"].append("P1: TODO/FIXME found — plan manquant")
        results["P1_think_before_coding"]["score"] -= 20
    if P1_PATTERNS["large_unexplained"](added):
        results["P1_think_before_coding"]["warnings"].append("P1: >100 lignes sans explication — plan requis")
        results["P1_think_before_coding"]["score"] -= 25

    # P2: Simplicity
    if P2_PATTERNS["over_abstraction"].search("\n".join(added)):
        results["P2_simplicity"]["warnings"].append("P2: Abstraction suspecte (Factory/Strategy) — simplifier")
        results["P2_simplicity"]["score"] -= 30
    if P2_PATTERNS["speculative"].search("\n".join(added)):
        results["P2_simplicity"]["warnings"].append("P2: Code spéculatif — supprimer si pas utilisé")
        results["P2_simplicity"]["score"] -= 20
    if P2_PATTERNS["deep_nesting"](added):
        results["P2_simplicity"]["warnings"].append("P2: Nesting profond (>8 niveaux) — refactor")
        results["P2_simplicity"]["score"] -= 15
    if P2_PATTERNS["magic_numbers"](added):
        results["P2_simplicity"]["warnings"].append("P2: Nombres magiques — nommer en constantes")
        results["P2_simplicity"]["score"] -= 10

    # P3: Clean Diffs
    if not added or not removed:
        pass  # new file, no mixed concerns
    format_changes = [l for l in added if re.match(r"^[+-]\s*$", l)]
    if len(format_changes) > len(added) * 0.3:
        results["P3_clean_diffs"]["warnings"].append("P3: >30% de changements de formattage — commit séparé")
        results["P3_clean_diffs"]["score"] -= 25
    comment_dels = [l for l in removed if l.strip().startswith("-#")]
    if comment_dels:
        results["P3_clean_diffs"]["warnings"].append(f"P3: {len(comment_dels)} commentaires supprimés — intentionnel ?")
        results["P3_clean_diffs"]["score"] -= 10

    # P4: Verifiable Tests
    if P4_PATTERNS["no_test"](added):
        results["P4_verifiable_tests"]["warnings"].append("P4: Aucun test détecté — ajouter des assertions")
        results["P4_verifiable_tests"]["score"] -= 30
    if P4_PATTERNS["self_review"](added + removed):
        results["P4_verifiable_tests"]["warnings"].append("P4: Auto-review suspect — faire vérifier par un agent séparé")
        results["P4_verifiable_tests"]["score"] -= 20

    return results


def format_report(results: dict) -> str:
    """Format review results as readable text."""
    total = 0
    lines = ["🧠 Karpathy Code Review", "═" * 40]

    for key, data in results.items():
        total += data["score"] / 4
        label = key.replace("_", " ").upper()
        status = "✅" if data["score"] >= 80 else "⚠️" if data["score"] >= 50 else "❌"
        lines.append(f"\n{status} {label} (score: {data['score']}/100)")
        for w in data["warnings"]:
            lines.append(f"  • {w}")
        if not data["warnings"]:
            lines.append(f"  ✓ Aucun problème")

    lines.append(f"\n{'═' * 40}")
    lines.append(f"Score global: {total:.0f}/100")
    if total >= 80:
        lines.append("✅ Prêt pour review")
    elif total >= 50:
        lines.append("⚠️  Corriger les warnings avant merge")
    else:
        lines.append("❌ Revoir en profondeur")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", type=str, help="Path to diff file")
    parser.add_argument("--file", type=str, help="Path to source file")
    parser.add_argument("--git", type=str, help="Git ref (e.g., HEAD~3)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    diff_text = ""
    if args.diff:
        diff_text = Path(args.diff).read_text(encoding="utf-8")
    elif args.file:
        diff_text = Path(args.file).read_text(encoding="utf-8")
        # Fake diff for single file review
        lines = diff_text.split("\n")
        diff_text = "\n".join(f"+{l}" for l in lines)
    elif args.git:
        import subprocess
        diff_text = subprocess.check_output(["git", "diff", args.git], text=True)
    else:
        print("Provide --diff, --file, or --git")
        sys.exit(1)

    results = review_diff(diff_text)
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(format_report(results))