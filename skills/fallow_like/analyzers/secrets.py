"""Secrets and unsafe exports detection."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult
from skills.fallow_like.models import SecretFinding, Severity
import re
import math


class SecretsAnalyzer:
    SECRET_PATTERNS = [
        (r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']([A-Za-z0-9_\-]{16,})["\']', "api_key"),
        (r'(?:secret[_-]?key)\s*[:=]\s*["\']([A-Za-z0-9_\-]{16,})["\']', "api_key"),
        (r'(?:access[_-]?token|accesstoken)\s*[:=]\s*["\']([A-Za-z0-9_\-\.]{16,})["\']', "token"),
        (r'(?:auth[_-]?token)\s*[:=]\s*["\']([A-Za-z0-9_\-\.]{16,})["\']', "token"),
        (r'(?:bearer\s+)([A-Za-z0-9_\-\.]{16,})', "token"),
        (r'(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{8,})["\']', "password"),
        (r'(?:private[_-]?key)\s*[:=]\s*["\']([^"\']{32,})', "private_key"),
        (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "private_key"),
        (r'(?:AKIA[0-9A-Z]{16})', "api_key"),
        (r'(?:AIza[0-9A-Za-z_\-]{35})', "api_key"),
        (r'(?:ghp_[0-9a-zA-Z]{36})', "token"),
        (r'(?:sk-[0-9a-zA-Z]{48})', "api_key"),
        (r'(?:mongodb|mysql|postgres|redis)://[^:]+:[^@]+@', "password"),
        (r'export\s+(?:default\s+)?(?:const|let|var)\s+\w*[Pp]assword', "export"),
        (r'export\s+(?:default\s+)?(?:const|let|var)\s+\w*[Ss]ecret', "export"),
        (r'export\s+(?:default\s+)?(?:const|let|var)\s+\w*[Tt]oken', "export"),
        (r'export\s+(?:default\s+)?(?:const|let|var)\s+\w*[Kk]ey(?!word)', "export"),
    ]

    EXCLUDE_PATTERNS = [
        'example', 'placeholder', 'your_', 'my_', 'test_',
        r'xxx+', r'0000', r'1234', r'abcd', 'fake', 'dummy',
        r'process\.env', r'os\.environ', r'config\[', 'getenv',
        r'ENV\[', r'Settings\.', r'\.env\.',
    ]

    EXCLUDE_FILES = ['.env.example', '.env.template', '.env.sample', 'test', 'spec', 'mock']

    def analyze(self, scan: ScanResult) -> list:
        findings = []

        for file_ast in scan.files:
            if any(p in file_ast.path for p in self.EXCLUDE_FILES):
                continue

            try:
                text = file_ast.source.decode("utf-8", errors="replace")
            except Exception:
                continue

            lines = text.splitlines()

            for pattern, secret_type in self.SECRET_PATTERNS:
                for match in re.finditer(pattern, text):
                    matched = match.group(0)

                    if any(re.search(ex, matched, re.IGNORECASE) for ex in self.EXCLUDE_PATTERNS):
                        continue

                    line_num = text[:match.start()].count("\n") + 1
                    line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""
                    entropy = self._calc_entropy(matched)

                    findings.append(SecretFinding(
                        rule_id="SEC001",
                        severity=Severity.CRITICAL if secret_type in ("private_key", "password") else Severity.ERROR,
                        message=f"Potential {secret_type.replace('_', ' ')} hardcoded",
                        file=file_ast.path,
                        line=line_num,
                        snippet=line_content[:100],
                        secret_type=secret_type,
                        pattern_matched=pattern[:50],
                        entropy=round(entropy, 2),
                        confidence=min(0.5 + entropy / 10, 0.95),
                        fix_hint="Move to environment variable or secrets manager",
                    ))

        return findings

    def _calc_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        freq = {}
        for c in text:
            freq[c] = freq.get(c, 0) + 1
        length = len(text)
        return -sum((count / length) * math.log2(count / length) for count in freq.values())