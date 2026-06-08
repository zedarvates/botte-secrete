"""Markdown output formatter."""

from __future__ import annotations
from skills.fallow_like.models import AnalysisResult
from datetime import datetime

EMOJI = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🔴"}


def format(result: AnalysisResult) -> str:
    lines = [
        "# 🔬 Fallow-Like Analysis Report",
        "",
        f"**Project:** `{result.project_root}`",
        f"**Date:** {datetime.utcnow().isoformat()}Z",
        f"**Health:** {result.health.score}/100 ({result.health.grade})",
        f"**Duration:** {result.duration_seconds:.1f}s",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files analyzed | {result.stats.total_files} |",
        f"| Total lines | {result.stats.total_lines} |",
        f"| Dead code | {len(result.dead_code)} |",
        f"| Duplication | {len(result.duplication)} |",
        f"| Complexity | {len(result.complexity)} |",
        f"| Boundary violations | {len(result.boundaries)} |",
        f"| Feature flags | {len(result.feature_flags)} |",
        f"| Secrets | {len(result.secrets)} |",
        f"| Hot paths | {len(result.hot_paths)} |",
        f"| Blast radius | {len(result.blast_radius)} |",
        "",
    ]

    sections = [
        ("🔴 Secrets", result.secrets),
        ("❌ Boundary Violations", result.boundaries),
        ("❌ Complexity", result.complexity),
        ("⚠️ Dead Code", result.dead_code),
        ("⚠️ Duplication", result.duplication),
        ("⚠️ Feature Flags", result.feature_flags),
        ("🔥 Hot Paths", result.hot_paths),
        ("💥 Blast Radius", result.blast_radius),
    ]

    for title, findings in sections:
        if not findings:
            continue
        lines.append(f"## {title}")
        lines.append("")
        for f in findings[:50]:
            emoji = EMOJI.get(f.severity.value, "•")
            lines.append(f"- {emoji} **{f.file}:{f.line}** — {f.message}")
            if f.fix_hint:
                lines.append(f"  → *Fix: {f.fix_hint}*")
        if len(findings) > 50:
            lines.append(f"- ... and {len(findings) - 50} more")
        lines.append("")

    return "\n".join(lines)
