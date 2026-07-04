#!/usr/bin/env python3
"""Verify every command cited in README.md actually runs.

    python scripts/test_readme_commands.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 30


def extract_commands(readme: Path) -> list[str]:
    text = readme.read_text(encoding="utf-8")
    commands = []
    in_block = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if in_block and not line.strip().startswith("#"):
            cmd = line.strip()
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
