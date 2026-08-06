#!/usr/bin/env python3
"""Security regression tests for project remote detection."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.skill_project_optimizer.profiler import profile_project


def _profile_remote(remote: str) -> bool:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        git_dir = root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text(
            f'[remote "origin"]\n\turl = {remote}\n',
            encoding="utf-8",
        )
        return profile_project(str(root)).has_github_remote


def main() -> int:
    cases = {
        "https remote": (_profile_remote("https://github.com/org/repo.git"), True),
        "ssh remote": (_profile_remote("git@github.com:org/repo.git"), True),
        "lookalike host": (_profile_remote("https://github.com.evil.example/repo"), False),
        "path substring": (_profile_remote("https://example.com/github.com/repo"), False),
    }
    failed = [name for name, (actual, expected) in cases.items() if actual != expected]
    for name in cases:
        print(f"  [{'FAIL' if name in failed else 'PASS'}] {name}")
    print(f"\nRESULT: {len(cases) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
