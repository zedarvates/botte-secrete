#!/usr/bin/env python3
"""Porthos Audit Script — Run fallow-like analysis on a project."""

import sys
import json
import datetime
from pathlib import Path

# Setup path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from skills.fallow_like.scanner import ProjectScanner
from skills.fallow_like.analyzers.dead_code import DeadCodeAnalyzer
from skills.fallow_like.analyzers.duplication import DuplicationAnalyzer
from skills.fallow_like.analyzers.complexity import ComplexityAnalyzer
from skills.fallow_like.analyzers.secrets import SecretsAnalyzer
from skills.fallow_like.analyzers.boundaries import BoundaryAnalyzer
from skills.fallow_like.analyzers.feature_flags import FeatureFlagAnalyzer
from skills.fallow_like.health import calculate_health


def main():
    if len(sys.argv) < 3:
        print("Usage: porthos_audit.py <project_path> <output_dir>")
        sys.exit(1)

    project_path = sys.argv[1]
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔬 Porthos — Scanning {project_path}...")

    # Scan
    scanner = ProjectScanner(
        project_path,
        ignore_patterns=[
            ".git/", "node_modules/", "__pycache__/", ".venv/", "venv/",
            "*.min.js", ".next/", "coverage/", "dist/", "build/", ".mypy_cache/",
        ],
    )
    scan_result = scanner.scan()
    print(f"  Scanned {len(scan_result.files)} files, {scan_result.stats['total_lines']} lines")

    # Run analyzers
    print("  Running analyzers...")
    dead_code = DeadCodeAnalyzer().analyze(scan_result)
    print(f"    Dead code: {len(dead_code)}")

    duplication = DuplicationAnalyzer().analyze(scan_result)
    print(f"    Duplication: {len(duplication)}")

    complexity = ComplexityAnalyzer().analyze(scan_result)
    print(f"    Complexity: {len(complexity)}")

    secrets = SecretsAnalyzer().analyze(scan_result)
    print(f"    Secrets: {len(secrets)}")

    boundaries = BoundaryAnalyzer().analyze(scan_result)
    print(f"    Boundaries: {len(boundaries)}")

    feature_flags = FeatureFlagAnalyzer().analyze(scan_result)
    print(f"    Feature flags: {len(feature_flags)}")

    # Health (pass analyzer results)
    health = calculate_health(
        scan_result,
        dead_code=dead_code,
        duplication=duplication,
        complexity=complexity,
        secrets=secrets,
        boundaries=boundaries,
        feature_flags=feature_flags,
    )

    # Compile report
    report = {
        "project": project_path,
        "date": datetime.datetime.now().isoformat(),
        "auditor": "Porthos",
        "files_analyzed": len(scan_result.files),
        "total_lines": scan_result.stats["total_lines"],
        "health_score": health.score,
        "health_grade": health.grade,
        "findings": {"critical": [], "error": [], "warning": [], "info": [], "total": 0},
        "dead_code": [dc.model_dump() for dc in dead_code],
        "duplication": [d.model_dump() for d in duplication],
        "complexity": [c.model_dump() for c in complexity],
        "secrets": [s.model_dump() for s in secrets],
        "boundaries": [b.model_dump() for b in boundaries],
        "feature_flags": [ff.model_dump() for ff in feature_flags],
        "recommendations": [],
    }

    # Categorize findings
    all_findings = []
    all_findings.extend([{**dc.model_dump(), "severity": "error", "type": "dead_code"} for dc in dead_code])
    all_findings.extend([{**d.model_dump(), "severity": "warning", "type": "duplication"} for d in duplication])
    all_findings.extend([{**c.model_dump(), "severity": "warning" if c.complexity > 10 else "info", "type": "complexity"} for c in complexity])
    all_findings.extend([{**s.model_dump(), "severity": s.severity, "type": "secret"} for s in secrets])
    all_findings.extend([{**b.model_dump(), "severity": "error", "type": "boundary"} for b in boundaries])
    all_findings.extend([{**ff.model_dump(), "severity": "info", "type": "feature_flag"} for ff in feature_flags])

    seen = set()
    for f in all_findings:
        sev = f.get("severity", "info")
        key = f.get("file", "") + f.get("description", "")
        if key in seen:
            continue
        seen.add(key)

        if sev in ("critical",):
            report["findings"]["critical"].append(f)
        elif sev in ("error",):
            report["findings"]["error"].append(f)
        elif sev == "warning":
            report["findings"]["warning"].append(f)
        else:
            report["findings"]["info"].append(f)
        report["findings"]["total"] += 1

    # Recommendations
    if secrets:
        report["recommendations"].append({"priority": "CRITIQUE", "description": f"Corriger {len(secrets)} expositions de secrets"})
    if dead_code:
        report["recommendations"].append({"priority": "HAUTE", "description": f"Supprimer {len(dead_code)} symboles morts"})
    if duplication:
        report["recommendations"].append({"priority": "HAUTE", "description": f"Réduire {len(duplication)} duplications"})
    if boundaries:
        report["recommendations"].append({"priority": "MOYEN", "description": f"Réparer {len(boundaries)} violations architecture"})
    high_complexity = [c for c in complexity if c.complexity > 15]
    if high_complexity:
        report["recommendations"].append({"priority": "MOYEN", "description": f"Refactoriser {len(high_complexity)} fonctions trop complexes (CC>15)"})
    stale_ff = [ff for ff in feature_flags if ff.stale]
    if stale_ff:
        report["recommendations"].append({"priority": "BAS", "description": f"Nettoyer {len(stale_ff)} feature flags stale"})

    # Save
    output_base = output_dir / "audit-report"
    with open(str(output_base) + ".json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n📊 Health: {health.score}/100 ({health.grade})")
    print(f"📊 Findings: {report['findings']['total']}")
    print(f"   Error: {len(report['findings']['error'])}")
    print(f"   Warning: {len(report['findings']['warning'])}")
    print(f"   Info: {len(report['findings']['info'])}")
    print(f"\n✅ Report saved to {output_base}.json")


if __name__ == "__main__":
    main()
