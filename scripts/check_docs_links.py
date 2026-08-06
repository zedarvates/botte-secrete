#!/usr/bin/env python3
"""Check local Markdown links in GitHub-facing documentation."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO = Path(__file__).resolve().parent.parent
DEFAULT_PATHS = [
    REPO / "README.md",
    REPO / "README.fr.md",
    REPO / "AGENTS.md",
    REPO / "CONTRIBUTING.md",
    REPO / "SECURITY.md",
    REPO / "docs",
    REPO / ".github",
]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REMOTE_SCHEMES = {"http", "https", "mailto"}


def markdown_files(paths: list[Path]) -> list[Path]:
    """Return unique Markdown files under explicit files and directories."""
    files: set[Path] = set()
    for path in paths:
        resolved = path if path.is_absolute() else (REPO / path)
        if resolved.is_file() and resolved.suffix.casefold() == ".md":
            files.add(resolved.resolve())
        elif resolved.is_dir():
            files.update(item.resolve() for item in resolved.rglob("*.md"))
    return sorted(files)


def _target(raw: str) -> str:
    """Extract a local target while tolerating Markdown titles and <paths>."""
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1:value.index(">")]
    return value.split(maxsplit=1)[0]


def broken_links(path: Path) -> list[tuple[int, str]]:
    """Return missing local link targets outside fenced code blocks."""
    failures: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in LINK_RE.finditer(line):
            target = _target(match.group(1))
            if not target or target.startswith("#"):
                continue
            parsed = urlsplit(target)
            if parsed.scheme.casefold() in REMOTE_SCHEMES:
                continue
            if parsed.scheme or target.startswith("//"):
                continue
            local = unquote(parsed.path)
            candidate = (path.parent / local).resolve()
            if not candidate.exists():
                failures.append((number, target))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    files = markdown_files(args.paths or DEFAULT_PATHS)
    failures: list[tuple[Path, int, str]] = []
    for path in files:
        failures.extend((path, line, target) for line, target in broken_links(path))

    if failures:
        for path, line, target in failures:
            print(f"{path.relative_to(REPO)}:{line}: missing local target: {target}")
        print(f"{len(failures)} broken link(s) across {len(files)} Markdown file(s)")
        return 1

    print(f"{len(files)} Markdown file(s), 0 broken local links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
