"""readers — READ, GLOB, GREP wrappers stdlib-only.

Usage:
    from skills.fast_context.readers import fast_read, fast_glob, fast_grep

    lines = fast_read("main.py")            # Read file, return lines
    files = fast_glob("**/*.py", ".")       # Glob with gitignore respect
    matches = fast_grep("def ", ".")        # grep pattern → (file, line, text)
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import re
from pathlib import Path
from typing import Optional

# Extensions binaires à ignorer
_BINARY_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".o", ".a", ".lib",
    ".lock", ".sum",
    ".db", ".sqlite",
})

# Dossiers à ignorer
_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".botte-cache", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info",
    ".hermes", ".cursor", ".vscode", ".idea",
})


def _should_skip(path: Path) -> bool:
    """Skip binary files, hidden dirs, and known nuisances."""
    name = path.name
    if name.startswith(".") and path.is_dir():
        return name in _SKIP_DIRS or name not in (".github", ".env.example")
    if name in _SKIP_DIRS:
        return True
    if path.suffix.lower() in _BINARY_EXTS:
        return True
    return False


def _is_binary(content: bytes, sample_size: int = 8192) -> bool:
    """Detect binary content by checking for null bytes in the first sample."""
    sample = content[:sample_size]
    return b"\x00" in sample


def fast_read(filepath: str, max_lines: int = 200) -> list[str]:
    """Read a file, return up to max_lines lines.

    Handles UTF-8 and latin-1; returns [] on binary or error.
    Detects binary files by checking for null bytes.
    """
    p = Path(filepath)
    if not p.exists() or not p.is_file():
        return []
    if _should_skip(p):
        return []
    try:
        raw = p.read_bytes()
    except OSError:
        return []
    if _is_binary(raw):
        return []
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"# … {len(lines)} more lines truncated")
    return lines


def fast_glob(pattern: str, root: str = ".") -> list[str]:
    """Glob with skip logic, returns absolute paths sorted by mtime (newest first)."""
    root_p = Path(root).resolve()
    hits: list[Path] = []
    for p in root_p.rglob(pattern):
        rel = p.relative_to(root_p)
        parts = rel.parts
        if any(part in _SKIP_DIRS or (part.startswith(".") and part != ".") for part in parts):
            continue
        if p.is_file() and p.suffix.lower() not in _BINARY_EXTS:
            hits.append(p)
    hits.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return [str(h) for h in hits]


def fast_grep(pattern: str, root: str = ".", max_matches: int = 100) -> list[dict]:
    """Grep pattern dans root, retourne [{file, line, text, line_num}, ...].

    Utilise `grep -rn` pour les gros repos (>500 fichiers), sinon regex Python.
    """
    root_p = Path(root).resolve()
    total_py = len(list(root_p.rglob("*.py")))
    use_subprocess = total_py > 500

    if use_subprocess:
        return _grep_subprocess(pattern, root_p, max_matches)

    return _grep_python(pattern, root_p, max_matches)


def _grep_subprocess(pattern: str, root: Path, max_matches: int) -> list[dict]:
    """grep -rnI via subprocess (rapide pour gros repos)."""
    try:
        result = subprocess.run(
            ["grep", "-rnI", "--include=*.py", "--include=*.rs", "--include=*.ts",
             "--include=*.js", "--include=*.toml", "--include=*.yaml",
             "--include=*.yml", "--include=*.md", "--include=*.json",
             "-m", "3", pattern, str(root)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _grep_python(pattern, root, max_matches)

    matches: list[dict] = []
    for line in result.stdout.splitlines()[:max_matches]:
        # Format: file:line_num:text
        parts = line.split(":", 2)
        if len(parts) >= 2:
            f = parts[0]
            ln = int(parts[1]) if parts[1].isdigit() else 0
            txt = parts[2] if len(parts) > 2 else ""
            matches.append({"file": f, "line_num": ln, "text": txt})
    return matches


def _grep_python(pattern: str, root: Path, max_matches: int) -> list[dict]:
    """Regex Python (portable, sans dépendance grep)."""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return []
    matches: list[dict] = []
    for p in root.rglob("*"):
        if _should_skip(p) or not p.is_file():
            continue
        if p.suffix.lower() in _BINARY_EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append({
                    "file": str(p),
                    "line_num": i,
                    "text": line.strip(),
                })
                if len(matches) >= max_matches:
                    return matches
    return matches


def get_file_stats(filepath: str) -> dict:
    """Retourne {size, lines, mtime} pour un fichier."""
    p = Path(filepath)
    try:
        stat = p.stat()
        return {
            "size": stat.st_size,
            "lines": len(fast_read(filepath, max_lines=1)),
            "mtime": int(stat.st_mtime),
        }
    except OSError:
        return {"size": 0, "lines": 0, "mtime": 0}
