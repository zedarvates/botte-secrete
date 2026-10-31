#!/usr/bin/env python3
"""Check local Markdown links in GitHub-facing documentation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from skills.fallow_like.local_links import extract_markdown_links  # noqa: E402
DEFAULT_PATHS = [
    REPO / "README.md",
    REPO / "README.fr.md",
    REPO / "AGENTS.md",
    REPO / "CONTRIBUTING.md",
    REPO / "SECURITY.md",
    REPO / "docs",
    REPO / ".github",
]
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


def inspect_links(path: Path) -> dict:
    """Return known missing paths plus explicit limits of the shared parser."""
    failures: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8")
    extracted = extract_markdown_links(text, max_links=50000)
    reasons = {issue["reason"] for issue in extracted["issues"]}
    if extracted["truncated"]:
        reasons.add("max_links")
    if extracted["issues_omitted"]:
        reasons.add("additional_unsupported_syntax")
    for link in extracted["links"]:
        number, target = link["line"], link["target"]
        if not target or target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("//"):
            continue
        local = unquote(parsed.path)
        candidate = (path.parent / local).resolve()
        if not candidate.exists():
            failures.append((number, target))
    return {"failures": failures, "partial_reasons": sorted(reasons)}


def broken_links(path: Path) -> list[tuple[int, str]]:
    """Compatibility helper: known missing local targets in supported syntax."""
    return inspect_links(path)["failures"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--strict-coverage", action="store_true",
                        help="return 3 when any document was only partially checked")
    args = parser.parse_args(argv)
    files = markdown_files(args.paths or DEFAULT_PATHS)
    failures: list[tuple[Path, int, str]] = []
    partial = False
    for path in files:
        try:
            result = inspect_links(path)
            failures.extend((path, line, target) for line, target in result["failures"])
            if result["partial_reasons"]:
                partial = True
                print(f"{path}: partial local-link check: " + ", ".join(result["partial_reasons"]))
        except (OSError, UnicodeError, ValueError) as exc:
            partial = True
            print(f"{path}: partial local-link check: {exc}")

    if failures:
        for path, line, target in failures:
            display = path.relative_to(REPO) if path.is_relative_to(REPO) else path
            print(f"{display}:{line}: missing local target: {target}")
        print(f"{len(failures)} broken link(s) across {len(files)} Markdown file(s)")
        return 3 if partial and args.strict_coverage else 1

    if partial:
        print(f"{len(files)} Markdown file(s), local-link check incomplete")
        return 3 if args.strict_coverage else 0
    print(f"{len(files)} Markdown file(s), 0 broken local links")
    return 0


if __name__ == "__main__":
    sys.exit(main())

