"""Historical secrets scanner — check git history for credential leaks.

    python -m skills.security_scanner.history [<project>]

Scans git log for patterns like API keys, tokens, passwords in commit diffs.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Patterns to detect in git history
_SECRET_PATTERNS = [
    (r'(?:api[_-]?key|apikey|API_KEY)\s*[:=]\s*["\']?([\w\-]{20,})', "API key"),
    (r'(?:token|TOKEN)\s*[:=]\s*["\']?([\w\-\.]{20,})', "token"),
    (r'(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{4,})', "password"),
    (r'(?:secret|SECRET)\s*[:=]\s*["\']?([\w\-]{10,})', "secret"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI/DeepSeek API key"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub PAT"),
    (r'-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY', "private key"),
]


def scan_history(project: str | Path = ".") -> dict:
    project = Path(project).resolve()
    findings = []

    try:
        proc = subprocess.run(
            ["git", "log", "--all", "--patch", "--no-color", "-S", "key",
             "--", "*.py", "*.sh", "*.yaml", "*.yml", "*.json", "*.toml", "*.env"],
            cwd=project, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return {"project": str(project), "findings": [], "error": "git failed"}

    for line in proc.stdout.splitlines():
        if line.startswith("+") or line.startswith("-"):
            for pattern, label in _SECRET_PATTERNS:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    findings.append({
                        "type": label,
                        "match": m.group(0)[:40] + "...",
                        "line": line.strip()[:120],
                    })

    return {"project": str(project), "findings": findings[:20], "total": len(findings)}


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else "."
    result = scan_history(project)
    print(f"🔍 Git history scan — {result['project']}")
    if result.get("error"):
        print(f"   {result['error']}")
        return
    print(f"   {result['total']} potential secrets found")
    for f in result["findings"][:10]:
        print(f"   [{f['type']}] {f['match']}")


if __name__ == "__main__":
    main()
