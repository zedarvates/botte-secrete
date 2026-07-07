#!/usr/bin/env python3
"""Verify every command cited in README.md actually runs.

    python scripts/test_readme_commands.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skills.console_utf8 import force_utf8  # noqa: E402 — avant tout print d'émoji

force_utf8()

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 30


def extract_commands(readme: Path) -> list[str]:
    """Shell-runnable lines from ```bash fences only — ```python fences hold
    import snippets, not shell commands, and were previously fed to shell=True
    verbatim (guaranteed failures, not real README bugs)."""
    text = readme.read_text(encoding="utf-8")
    commands = []
    in_bash_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_bash_block = stripped[3:].strip().lower() == "bash"
            continue
        if in_bash_block and not stripped.startswith("#"):
            cmd = stripped
            if cmd and not cmd.startswith("$ "):
                commands.append(cmd)
            elif cmd.startswith("$ "):
                commands.append(cmd[2:])
    return commands


def main():
    readme = REPO / "README.md"
    if not readme.exists():
        print("README.md not found")
        return 0

    commands = extract_commands(readme)
    passed = failed = skipped = 0
    for cmd in commands:
        if any(s in cmd for s in ["gh ", "git push", "pip install", "cargo ", "curl "]):
            skipped += 1
            continue
        try:
            r = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True,
                               text=True, timeout=TIMEOUT,
                               env={**__import__("os").environ, "PYTHONPATH": str(REPO)})
            if r.returncode == 0:
                passed += 1
            else:
                failed += 1
                print(f"  FAIL {cmd[:80]}")
        except Exception:
            failed += 1
            print(f"  ERR  {cmd[:80]}")

    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
