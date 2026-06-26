"""report — compile scanning results into compact reports.

Formats:
    compact: file:line  [severity] pattern — snippet
    json:    machine-readable
    markdown:  human-readable with severity badges
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Finding:
    file: str
    line: int
    column: int
    pattern: str
    severity: str
    snippet: str = ""


Severity = str  # "critical" | "error" | "warning" | "info"


@dataclass
class ScanReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding):
        self.findings.append(finding)

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        for f in self.findings:
            sev = f.severity if f.severity in counts else "info"
            counts[sev] += 1
        return counts

    @property
    def has_critical(self) -> bool:
        return self.by_severity.get("critical", 0) > 0

    @property
    def has_errors(self) -> bool:
        return self.by_severity.get("error", 0) > 0

    def compact(self) -> str:
        """Format: file:line  [severity] pattern — snippet"""
        lines = []
        sorted_findings = sorted(self.findings, key=lambda f: (
            {"critical": 0, "error": 1, "warning": 2, "info": 3}.get(f.severity, 99),
            f.file, f.line
        ))
        for f in sorted_findings:
            file_short = _shorten_path(f.file, 40)
            sev_tag = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}.get(f.severity, "⚪")
            snippet = f.snippet[:60] if f.snippet else ""
            lines.append(f"{sev_tag} {file_short}:{f.line}  [{f.severity}] {f.pattern} — {snippet}")
        if lines:
            lines.insert(0, f"🔍 Security scan: {self.count} findings "
                          f"(🔴{self.by_severity['critical']} 🟠{self.by_severity['error']} "
                          f"🟡{self.by_severity['warning']} 🔵{self.by_severity['info']})")
            lines.insert(1, "")
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """JSON format with all fields."""
        data = {
            "summary": {
                "total": self.count,
                **self.by_severity,
            },
            "findings": [asdict(f) for f in self.findings],
        }
        return json.dumps(data, ensure_ascii=False, indent=indent)

    def markdown(self) -> str:
        """Markdown format with severity badges."""
        if not self.findings:
            return "✅ **Clean** — no security issues found."

        lines = ["## 🔍 Security Scan Report\n"]
        lines.append(f"**{self.count} findings total** — "
                     f"🔴 {self.by_severity['critical']} critical | "
                     f"🟠 {self.by_severity['error']} error | "
                     f"🟡 {self.by_severity['warning']} warning | "
                     f"🔵 {self.by_severity['info']} info\n")

        sev_emoji = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}
        current_file = ""
        for f in sorted(self.findings, key=lambda x: (x.file, x.line)):
            if f.file != current_file:
                current_file = f.file
                lines.append(f"\n### `{current_file}`\n")
            emoji = sev_emoji.get(f.severity, "⚪")
            snippet = f.snippet[:80] if f.snippet else ""
            lines.append(f"|{emoji}|{f.line}|`{snippet}`|{f.severity} `{f.pattern}`|")

        return "\n".join(lines)


def _shorten_path(path: str, max_len: int = 40) -> str:
    """Shorten a path to max_len by taking the last part and prefixing with …"""
    if len(path) <= max_len:
        return path
    parts = path.split("/")
    short = ""
    for part in reversed(parts):
        candidate = f"{part}/{short}" if short else part
        if len(candidate) > max_len - 3:  # space for "…/"
            break
        short = candidate
    return f"…/{short}"


def scan_report(findings: list[Finding]) -> ScanReport:
    """Build a ScanReport from a list of findings."""
    return ScanReport(findings=findings)
