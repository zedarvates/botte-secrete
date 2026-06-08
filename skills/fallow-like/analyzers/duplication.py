"""Code duplication detection using token fingerprinting."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult
from skills.fallow_like.models import DuplicationFinding, Severity
import hashlib


class DuplicationAnalyzer:
    def __init__(self, min_lines: int = 6, min_tokens: int = 50):
        self.min_lines = min_lines
        self.min_tokens = min_tokens

    def analyze(self, scan: ScanResult) -> list:
        findings = []
        file_lines: dict[str, list[str]] = {}
        for file_ast in scan.files:
            try:
                text = file_ast.source.decode("utf-8", errors="replace")
                file_lines[file_ast.path] = text.splitlines()
            except Exception:
                continue

        hash_to_files: dict[str, list[tuple[str, int]]] = {}
        for fpath, lines in file_lines.items():
            for i in range(len(lines) - self.min_lines + 1):
                block = "\n".join(lines[i:i + self.min_lines])
                normalized = " ".join(block.lower().split())
                if len(normalized.split()) >= self.min_tokens // 10:
                    h = hashlib.md5(normalized.encode()).hexdigest()[:12]
                    if h not in hash_to_files:
                        hash_to_files[h] = []
                    hash_to_files[h].append((fpath, i + 1))

        seen = set()
        for h, locations in hash_to_files.items():
            if len(locations) < 2:
                continue
            unique_files = set(f for f, _ in locations)
            if len(unique_files) < 2:
                continue
            key = tuple(sorted(unique_files))
            if key in seen:
                continue
            seen.add(key)

            first_file, first_line = locations[0]
            second_file, second_line = locations[1]
            findings.append(DuplicationFinding(
                rule_id="DUP001",
                severity=Severity.WARNING,
                message=f"Code duplicated between {first_file}:{first_line} and {second_file}:{second_line}",
                file=first_file,
                line=first_line,
                duplicate_file=second_file,
                duplicate_line=second_line,
                duplicate_end_line=second_line + self.min_lines,
                lines_count=self.min_lines,
                confidence=0.85,
                fix_hint="Extract shared code into a common utility function",
            ))

        return findings
