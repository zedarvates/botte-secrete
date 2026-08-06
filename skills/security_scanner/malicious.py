"""scanner — scan orchestrator for security checking.

Itère les fichiers, applique regex + AST, agrège les résultats.
"""

from __future__ import annotations

import os
import re
import io
import tokenize
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
    ".zig-cache", "zig-out",
    "Library",  # Unity build/import cache (can hold multi-GB generated JSON)
})

# Source files are never legitimately this large; huge "source-looking" files
# are almost always generated/build artifacts (e.g. Unity's Library/Bee dag
# JSON, asset manifests) that would otherwise be read fully into memory and
# regex-scanned line by line, hanging the scan for minutes on a single file.
_MAX_SCAN_BYTES = 2 * 1024 * 1024

# These high-signal patterns describe executable syntax. In Python, a regex hit
# that starts inside a string, docstring, or comment is documentation/test data,
# not an executed operation. Other patterns keep their historical high-recall
# behavior because some intentionally inspect string contents (secrets, URLs).
_PYTHON_CODE_START_PATTERNS = frozenset({
    "exec_from_string", "pip_install_from_code", "requests_to_ip",
    "send_environ", "xor_obfuscation", "bytes_decode_obfuscation",
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
    if path.is_file():
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                return True
        except OSError:
            return True
    return False


def _python_non_code_spans(source: str) -> list[tuple[int, int]]:
    """Return absolute spans occupied by Python strings and comments."""
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    spans: list[tuple[int, int]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                continue
            start_row, start_col = token.start
            end_row, end_col = token.end
            spans.append((offsets[start_row - 1] + start_col,
                          offsets[end_row - 1] + end_col))
    except (IndentationError, tokenize.TokenError):
        return []
    return spans


def _scan_file_regex(source: str, filepath: str, pattern: Pattern,
                     non_code_spans: list[tuple[int, int]] | None = None) -> list[Finding]:
    """Scan a single file against one regex pattern."""
    findings: list[Finding] = []
    try:
        regex = re.compile(pattern.regex, re.IGNORECASE)
    except re.error:
        return findings

    absolute_offset = 0
    for i, line in enumerate(source.splitlines(keepends=True), 1):
        match = regex.search(line)
        if match:
            match_offset = absolute_offset + match.start()
            if non_code_spans and any(start <= match_offset < end
                                      for start, end in non_code_spans):
                absolute_offset += len(line)
                continue
            col = match.start()
            findings.append(Finding(
                file=filepath,
                line=i,
                column=col,
                pattern=pattern.name,
                severity=pattern.severity.value,
                snippet=line.strip()[:120],
            ))
        absolute_offset += len(line)
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
    python_non_code = (_python_non_code_spans(source)
                       if p.suffix == ".py" else [])

    # Regex scans (all patterns, all file types)
    for pattern_elem in PATTERNS:
        spans = (python_non_code
                 if pattern_elem.name in _PYTHON_CODE_START_PATTERNS else None)
        findings = _scan_file_regex(source, filepath, pattern_elem, spans)
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

    # Collect files, pruning skipped directories during the walk so we never
    # descend into node_modules / worktrees / build caches (rglob would still
    # traverse them fully before filtering, which is what made this hang).
    files_to_scan: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_p):
        dirnames[:] = [d for d in dirnames if not _should_skip(Path(dirpath) / d)]
        for fn in filenames:
            p = Path(dirpath) / fn
            if _should_skip(p):
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

    # Keep findings at least as severe as `fail_on` (critical=most severe).
    # Lower order number = more severe, so "at least as severe" is `<= min_level`.
    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    min_level = severity_order.get(fail_on, 1)
    filtered = [
        f for f in all_findings
        if severity_order.get(f.severity, 99) <= min_level
    ]

    return filtered
