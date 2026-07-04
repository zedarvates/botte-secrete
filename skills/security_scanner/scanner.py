"""
Security Scanner — lightweight credential leak and vulnerability detection.

Scans for:
- API keys / tokens
- Hardcoded passwords
- Path traversal
- Shell injection patterns
- Base64 secrets

Usage:
    from skills.security_scanner.scanner import scan
    issues = scan("api_key = 'sk-abc123'")
    # → [{issue: "API key detected", line: 1, severity: "high"}]
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SecurityIssue:
    """A detected security issue."""
    issue: str
    severity: str  # "critical", "high", "medium", "low"
    line: int
    column: int = 0
    snippet: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "issue": self.issue,
            "severity": self.severity,
            "line": self.line,
            "column": self.column,
            "snippet": self.snippet[:80],
            "suggestion": self.suggestion,
        }


# Patterns: (regex, issue, severity, suggestion)
CRITICAL_PATTERNS = [
    (r'(?i)(api[-_]?key|apikey)\s*[:=]\s*["\'][A-Za-z0-9_-]{20,}',
     "API key hardcoded", "critical", "Use env variable or secrets manager"),
    (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'][^"\']+',
     "Password hardcoded", "critical", "Use env variable or prompt"),
    (r'(?i)(secret|token|auth_token)\s*[:=]\s*["\'][A-Za-z0-9_-]{16,}',
     "Secret/token hardcoded", "critical", "Use config file or vault"),
    (r'(?i)(-----BEGIN\s+(RSA|PRIVATE|EC|DSA|OPENSSH)\s+KEY-----)',
     "Private key detected", "critical", "Remove from code, use env"),
]

HIGH_PATTERNS = [
    (r'(?i)exec\s*\(["\']|subprocess\.call|subprocess\.Popen',
     "Shell command execution", "high", "Use subprocess.run with shell=False"),
    (r'(?i)eval\s*\(|exec\s*\(|compile\s*\(',
     "Dynamic code execution", "high", "Avoid eval/exec, use safer alternatives"),
    (r'(?i)sleep\s*\(\d{3,}', "Long sleep (DoS risk)", "high", "Use asyncio.sleep or time-based backoff"),
    (r'(?i)pickle\.loads?|torch\.load|joblib\.load',
     "Unsafe deserialization", "high", "Use safe_load or verify source"),
]

MEDIUM_PATTERNS = [
    (r'(?i)(git|svn|hg)\s+clone|wget\s+|curl\s+.+-o',
     "Remote resource fetch", "medium", "Pin versions, verify checksums"),
    (r'os\.system\s*\(|os\.popen',
     "OS command execution", "medium", "Use subprocess.run with shell=False"),
    (r'(?i)(tmp|temp)\s*[:=]\s*["\']/tmp',
     "World-writable temp file", "medium", "Use tempfile.mkstemp() instead"),
    (r'(?i)rm\s+-rf\s+["\']?/["\']?',
     "Dangerous rm -rf /", "medium", "Be extremely careful with recursive delete"),
    (r'(?i)(\.env|\.secret|credentials\.)', "Potential credential file reference", "medium",
     "Ensure .env is in .gitignore"),
]

LOW_PATTERNS = [
    (r'base64\.(b64decode|b64encode)',
     "Base64 encoding (potential secret)", "low", "Verify intended use"),
    (r'(?i)(skip|ignore|bypass).*(check|verify|validation|auth)',
     "Security bypass comment", "low", "Remove before production"),
    (r'#\s*TODO.*(security|auth|permission|secret)',
     "Security TODO remaining", "low", "Address before deployment"),
]


def scan(content: str, filename: str = "unknown") -> dict:
    """Scan content for security issues.

    Returns:
        dict with total count, issues list, and summary
    """
    issues = []

    # Check each category
    for patterns, severity_name in [
        (CRITICAL_PATTERNS, "critical"),
        (HIGH_PATTERNS, "high"),
        (MEDIUM_PATTERNS, "medium"),
        (LOW_PATTERNS, "low"),
    ]:
        for pattern, description, _, suggestion in patterns:
            for i, line in enumerate(content.splitlines(), 1):
                m = re.search(pattern, line)
                if m:
                    start = max(0, m.start() - 10)
                    snippet = line[start:m.end() + 20].strip()
                    issues.append(SecurityIssue(
                        issue=description,
                        severity=severity_name,
                        line=i,
                        column=m.start() + 1,
                        snippet=snippet,
                        suggestion=suggestion,
                    ))

    return {
        "total": len(issues),
        "filename": filename,
        "by_severity": {
            "critical": sum(1 for i in issues if i.severity == "critical"),
            "high": sum(1 for i in issues if i.severity == "high"),
            "medium": sum(1 for i in issues if i.severity == "medium"),
            "low": sum(1 for i in issues if i.severity == "low"),
        },
        "issues": [i.to_dict() for i in issues],
        "pass": len(issues) == 0,
    }


def scan_file(path: str) -> dict:
    """Scan a single file."""
    p = Path(path)
    if not p.exists():
        return {"total": 0, "error": f"File not found: {path}", "pass": True}
    return scan(p.read_text(encoding="utf-8", errors="replace"), str(p))


def scan_directory(path: str, extensions: tuple = (".py", ".yaml", ".yml", ".json", ".env")) -> dict:
    """Scan a directory recursively."""
    p = Path(path)
    if not p.is_dir():
        return {"total": 0, "error": f"Not a directory: {path}", "pass": True}

    all_issues = []
    for ext in extensions:
        for f in p.rglob(f"*{ext}"):
            if "__pycache__" in str(f) or ".git" in str(f):
                continue
            result = scan_file(str(f))
            all_issues.extend(result["issues"])

    # Deduplicate by line and issue
    seen = set()
    unique = []
    for i in all_issues:
        key = (i["line"], i["issue"])
        if key not in seen:
            seen.add(key)
            unique.append(i)

    return {
        "total": len(unique),
        "files_scanned": len(list(p.rglob("*.*"))),
        "issues": unique,
        "by_severity": {
            "critical": sum(1 for i in unique if i["severity"] == "critical"),
            "high": sum(1 for i in unique if i["severity"] == "high"),
            "medium": sum(1 for i in unique if i["severity"] == "medium"),
            "low": sum(1 for i in unique if i["severity"] == "low"),
        },
        "pass": len(unique) == 0,
    }