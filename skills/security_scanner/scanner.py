"""scanner — scan orchestrator for security checking.

Itère les fichiers, applique regex + AST, agrège les résultats.
"""

from __future__ import annotations

import os
import re
import concurrent.futures
from pathlib import Path
from typing import Optional

from skills.security_scanner.patterns import PATTERNS, Pattern, Severity
from skills.security_scanner.ast_checker import analyze_ast as _analyze_ast
from skills.security_scanner.report import Finding, Severity as ReportSeverity


# Extensions et dossiers à ignorer
_SKIP_EXTS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".o", ".a", ".lib",
    ".lock", ".sum", ".db", ".sqlite",
    ".svg", ".pdf", ".doc", ".docx",
    ".exe", ".msi",
})
_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".botte-cache", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info",
    ".hermes", ".cursor", ".vscode", ".idea",
    "target",  # Rust build dir
})


def _should_skip(path: Path) -> bool:
    """Skip binary files, hidden dirs, and known nuisances."""
    name = path.name
    if name in _SKIP_DIRS:
        return True
    if name.startswith(".") and path.is_dir() and name not in (".github",):
        return True
    if path.suffix.lower() in _SKIP_EXTS:
        return True
    return False


def _scan_file_regex(source: str, filepath: str, pattern: Pattern) -> list[Finding]:
    """Scan a single file against one regex pattern."""
    findings: list[Finding] = []
    try:
        regex = re.compile(pattern.regex, re.IGNORECASE)
    except re.error:
        return findings

    for i, line in enumerate(source.splitlines(), 1):
        if regex.search(line):
            match = regex.search(line)
            col = match.start() if match else 0
            findings.append(Finding(
                file=filepath,
                line=i,
                column=col,
                pattern=pattern.name,
                severity=pattern.severity.value,
                snippet=line.strip()[:120],
            ))
    return findings


def _scan_file_single(filepath: str, do_ast: bool = True) -> list[Finding]:
    """Scan a single file with all patterns + AST."""
    p = Path(filepath)
    if _should_skip(p) or p.suffix.lower() not in (".py", ".rs", ".js", ".ts", ".sh", ".bash", ".yaml", ".yml", ".toml", ".json", ".md"):
        return []

    try:
        source = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    all_findings: list[Finding] = []

    # Regex scans (all patterns, all file types)
    for pattern_elem in PATTERNS:
        findings = _scan_file_regex(source, filepath, pattern_elem)
        all_findings.extend(findings)

    # AST scan (Python only)
    if do_ast and p.suffix == ".py":
        ast_findings = _analyze_ast(source, filepath)
        for f in ast_findings:
            all_findings.append(Finding(
                file=f["file"],
                line=f["line"],
                column=f.get("col", 0),
                pattern=f["pattern"],
                severity=f["severity"],
                snippet=f.get("detail", ""),
            ))

    return all_findings


def scan_file(filepath: str, do_ast: bool = True) -> list[Finding]:
    """Scan a single file. Returns list of Findings (empty = clean)."""
    return _scan_file_single(filepath, do_ast=do_ast)


def scan_dir(root: str, fail_on: str = "error", max_workers: int = 8,
             do_ast: bool = True) -> list[Finding]:
    """Scan a directory recursively with parallel workers.

    Args:
        root: Directory or file to scan.
        fail_on: Minimum severity to fail on (critical, error, warning, info).
        max_workers: Thread pool size.
        do_ast: Whether to run AST analysis on .py files.

    Returns:
        List of Findings.
    """
    root_p = Path(root).resolve()
    if not root_p.exists():
        return [Finding(file=root, line=0, column=0, pattern="not_found",
                        severity="error", snippet=f"Path does not exist: {root_p}")]

    if root_p.is_file():
        return scan_file(str(root_p), do_ast=do_ast)

    # Collect Python files
    files_to_scan: list[Path] = []
    for p in root_p.rglob("*"):
        if _should_skip(p):
            continue
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in (".py", ".rs", ".sh", ".bash", ".yaml", ".yml", ".toml", ".json", ".js", ".ts"):
            files_to_scan.append(p)

    if not files_to_scan:
        return []

    # Parallel scan
    all_findings: list[Finding] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_file_single, str(p), do_ast=do_ast): p
            for p in files_to_scan
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                results = future.result()
                all_findings.extend(results)
            except Exception as e:
                f = futures[future]
                all_findings.append(Finding(
                    file=str(f), line=0, column=0,
                    pattern="scan_error", severity="error",
                    snippet=f"Scan error: {e}",
                ))

    # Filter by fail_on severity
    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    min_level = severity_order.get(fail_on, 1)
    filtered = [
        f for f in all_findings
        if severity_order.get(f.severity, 99) >= min_level
    ]

    return filtered
