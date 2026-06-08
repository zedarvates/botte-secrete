#!/usr/bin/env python3
"""
fallow-python.py — Companion Python analyzer pour Fallow.

Analyse le code Python avec:
  - vulture (dead code)
  - radon (complexité)
  - ruff (lint)
  - pylint (duplication)

Usage:
  python3 fallow-python.py /path/to/project --format text
  python3 fallow-python.py /path/to/project --format json
"""

import os, sys, json, subprocess, tempfile
from pathlib import Path


def check_tool(name: str, install_cmd: str) -> bool:
    """Check if a tool is installed, return True/False."""
    try:
        subprocess.run([name, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def analyze_vulture(path: str) -> list[dict]:
    """Dead code detection with vulture."""
    findings = []
    try:
        r = subprocess.run(["vulture", path, "--min-confidence", "80"],
                          capture_output=True, text=True, timeout=60)
        for line in r.stdout.split("\n"):
            if "unused" in line.lower() or "dead" in line.lower():
                findings.append({"tool": "vulture", "message": line.strip()})
    except Exception as e:
        findings.append({"tool": "vulture", "error": str(e)})
    return findings


def analyze_radon(path: str) -> dict:
    """Complexity analysis with radon."""
    result = {"average_complexity": 0, "worst": [], "total_functions": 0, "c_grades": {}}
    try:
        r = subprocess.run(["radon", "cc", path, "-a", "-s", "-j"],
                          capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout) if r.stdout else {}
        complexities = []
        for filepath, functions in data.items():
            for func in functions:
                c = func.get("complexity", 0)
                complexities.append(c)
                if c > 10:
                    result["worst"].append({"file": filepath, "name": func.get("name", "?"), "complexity": c})
        if complexities:
            result["average_complexity"] = sum(complexities) / len(complexities)
            result["total_functions"] = len(complexities)
    except Exception as e:
        result["error"] = str(e)
    return result


def analyze_ruff(path: str) -> list[dict]:
    """Lint with ruff."""
    findings = []
    try:
        r = subprocess.run(["ruff", "check", path, "--quiet", "--output-format", "json"],
                          capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout) if r.stdout else []
        for item in data[:50]:
            findings.append({
                "tool": "ruff",
                "file": item.get("filename", ""),
                "line": item.get("location", {}).get("row", 0),
                "code": item.get("code", ""),
                "message": item.get("message", ""),
            })
    except Exception as e:
        findings.append({"tool": "ruff", "error": str(e)})
    return findings


def analyze_pylint_duplication(path: str) -> list[dict]:
    """Duplication detection with pylint."""
    findings = []
    try:
        r = subprocess.run(["pylint", path, "--disable=all", "--enable=duplicate-code"],
                          capture_output=True, text=True, timeout=120)
        for line in r.stdout.split("\n"):
            if "duplicate" in line.lower() or "similar" in line.lower():
                findings.append({"tool": "pylint", "message": line.strip()})
    except Exception as e:
        findings.append({"tool": "pylint", "error": str(e)})
    return findings


def score_from_findings(findings: dict) -> dict:
    """Calculate health score 0-100 from findings."""
    deductions = 0

    dead_reasons = len(findings.get("dead_code", []))
    deductions += min(dead_reasons * 5, 30)

    lint_errors = len(findings.get("lint", []))
    deductions += min(lint_errors * 2, 20)

    complexity = findings.get("complexity", {})
    avg = complexity.get("average_complexity", 0)
    if avg > 10:
        deductions += 15
    elif avg > 7:
        deductions += 10
    elif avg > 5:
        deductions += 5

    worst_count = len(complexity.get("worst", []))
    deductions += min(worst_count * 3, 15)

    dupes = len(findings.get("duplication", []))
    deductions += min(dupes * 5, 20)

    score = max(0, 100 - deductions)

    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D" if score >= 30 else "F",
        "deductions": deductions,
    }


def format_text(findings: dict, path: str) -> str:
    """Format findings as readable text."""
    sc = score_from_findings(findings)
    lines = [
        f"🔬 Fallow Python — Analyse de {path}",
        f"{'═' * 50}",
        f"Score: {sc['score']}/100 ({sc['grade']}) — {sc['deductions']} pts déduits",
        "",
    ]

    dc = findings.get("dead_code", [])
    if dc:
        lines.append(f"❌ Dead code: {len(dc)} trouvés")
        for f in dc[:10]:
            lines.append(f"  • {f['message'][:100]}")
        if len(dc) > 10:
            lines.append(f"  ... et {len(dc)-10} autres")

    comp = findings.get("complexity", {})
    if comp.get("average_complexity", 0) > 0:
        lines.append(f"\n📊 Complexité moyenne: {comp['average_complexity']:.1f} ({comp['total_functions']} fonctions)")
        for w in comp.get("worst", [])[:5]:
            lines.append(f"  ⚠️  {w['file']}:{w['name']} → {w['complexity']}")

    lint = findings.get("lint", [])
    if lint:
        lines.append(f"\n📋 Lint: {len(lint)} warnings")
        for f in lint[:10]:
            lines.append(f"  • {f['file']}:{f['line']} [{f['code']}] {f['message']}")

    dup = findings.get("duplication", [])
    if dup:
        lines.append(f"\n📋 Duplication: {len(dup)} trouvés")

    if not dc and not lint and not comp.get("worst"):
        lines.append("\n✅ Aucun problème détecté")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to analyze")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    findings = {
        "dead_code": analyze_vulture(args.path),
        "complexity": analyze_radon(args.path),
        "lint": analyze_ruff(args.path),
        "duplication": analyze_pylint_duplication(args.path),
    }

    if args.format == "json":
        print(json.dumps(findings, indent=2, default=str))
    else:
        print(format_text(findings, args.path))


if __name__ == "__main__":
    main()
