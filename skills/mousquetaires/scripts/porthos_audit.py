#!/usr/bin/env python3
"""Porthos Audit Script — Compact JSON output, cache-aware."""

import sys, json
from datetime import datetime
from pathlib import Path

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
from skills.cache import ProjectCache


def main():
    if len(sys.argv) < 3:
        print("Usage: porthos_audit.py <project_path> <output_dir>")
        sys.exit(1)

    project_path = sys.argv[1]
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔬 Porthos — Scanning {project_path}...")

    # Cache: check if already scanned
    cache = ProjectCache(project_path)
    cached = cache.get("scan-result")
    if cached:
        print("  📦 Using cached scan...")

    scanner = ProjectScanner(
        project_path,
        ignore_patterns=[".git/","node_modules/","__pycache__/",".venv/","venv/",
                        "*.min.js",".next/","coverage/","dist/","build/",".mypy_cache/"],
    )
    scan_result = scanner.scan()
    cache.set("scan-result", {"files": len(scan_result.files), "lines": scan_result.stats.get("total_lines", 0)})
    print(f"  Scanned {len(scan_result.files)} files, {scan_result.stats['total_lines']} lines")

    # Run analyzers
    print("  Running analyzers...")
    dead_code = DeadCodeAnalyzer().analyze(scan_result)
    duplication = DuplicationAnalyzer().analyze(scan_result)
    complexity = ComplexityAnalyzer().analyze(scan_result)
    secrets = SecretsAnalyzer().analyze(scan_result)
    boundaries = BoundaryAnalyzer().analyze(scan_result)
    feature_flags = FeatureFlagAnalyzer().analyze(scan_result)

    health = calculate_health(scan_result, dead_code=dead_code, duplication=duplication,
                              complexity=complexity, secrets=secrets, boundaries=boundaries,
                              feature_flags=feature_flags)

    # Build compact findings
    def to_fn(items, sev, typ):
        return [{"f": f"{i.file}:{i.line}" if hasattr(i,'line') else i.file,
                 "s": sev, "t": typ,
                 "d": (i.description[:80] if hasattr(i,'description') else str(i))}
                for i in items]

    findings = []
    findings.extend(to_fn(dead_code, "err", "dead"))
    findings.extend(to_fn(duplication, "warn", "dup"))
    findings.extend(to_fn([c for c in complexity if c.complexity > 15], "err", "cmp"))
    findings.extend(to_fn([c for c in complexity if 10 < c.complexity <= 15], "warn", "cmp"))
    findings.extend(to_fn(secrets, "crit" if any(hasattr(s,'severity') and s.severity=='critical' for s in secrets) else "err", "sec"))
    findings.extend(to_fn(boundaries, "err", "bnd"))
    findings.extend(to_fn(feature_flags, "warn", "flg"))

    # Compact report
    report = {
        "h": {"s": health.score, "g": health.grade},
        "st": {"f": len(scan_result.files), "l": scan_result.stats.get("total_lines", 0)},
        "fn": findings,
        "by": {"dead": len(dead_code), "dup": len(duplication), "cmp": len(complexity),
               "sec": len(secrets), "bnd": len(boundaries), "flg": len(feature_flags)},
        "rc": [],
    }

    # Recommendations (prioritized)
    if secrets:
        report["rc"].append({"p": "P0", "d": f"Corriger {len(secrets)} expositions de secrets"})
    if dead_code:
        report["rc"].append({"p": "P1", "d": f"Supprimer {len(dead_code)} symboles morts"})
    if duplication:
        report["rc"].append({"p": "P1", "d": f"Réduire {len(duplication)} duplications"})
    if boundaries:
        report["rc"].append({"p": "P1", "d": f"Réparer {len(boundaries)} violations architecture"})
    high_cmp = [c for c in complexity if c.complexity > 15]
    if high_cmp:
        report["rc"].append({"p": "P2", "d": f"Refactoriser {len(high_cmp)} fonctions complexes"})
    stale_ff = [ff for ff in feature_flags if ff.stale]
    if stale_ff:
        report["rc"].append({"p": "P2", "d": f"Nettoyer {len(stale_ff)} feature flags stale"})

    # Save & cache
    out = output_dir / "audit-report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    cache.set_audit_report(report)

    # Summary
    crit = sum(1 for f in findings if f["s"] == "crit")
    err = sum(1 for f in findings if f["s"] == "err")
    warn = sum(1 for f in findings if f["s"] == "warn")
    print(f"\n📊 Health: {health.score}/100 ({health.grade})")
    print(f"📊 Findings: {len(findings)} (🔴{crit} 🟠{err} 🟡{warn} ℹ️{len(findings)-crit-err-warn})")
    print(f"\n✅ Report saved to {out}")


if __name__ == "__main__":
    import sys as _sys  # ensure UTF-8 console on Windows (cp1252 crashes on emoji)
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass
    main()
