#!/usr/bin/env python3
"""Verify safely runnable commands cited in README.md.

    python scripts/test_readme_commands.py
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skills import __version__  # noqa: E402
from skills.console_utf8 import force_utf8  # noqa: E402 — avant tout print d'émoji

force_utf8()

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 30
# Checkup scans the supplied repository (AST, taint and patterns). The ordinary
# command-smoke deadline is too short for this growing repository on slower CI.
CHECKUP_TIMEOUT = 120
SAFE_BOTTE_COMMANDS = {
    "--help", "belt", "checkup", "discover", "doctor", "gain", "harvest",
    "upstreams",
}
BLOCKED_MODULES = {
    "skills.dashboard.api",
    "skills.hermes_bridge.mcp_server",
    "skills.universal_compressor.mcp_server",
}
BLOCKED_SCRIPTS = {
    (REPO / "scripts" / "generate_docs_visuals.py").resolve(),
    (REPO / "scripts" / "run_tests.py").resolve(),
    Path(__file__).resolve(),
}


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


def safe_argv(command: str) -> list[str] | None:
    """Return a shell-free argv for explicitly safe local command shapes."""
    if re.search(r"[;&|<>`]", command):
        return None
    try:
        argv = shlex.split(command, comments=True, posix=os.name != "nt")
    except ValueError:
        return None
    if not argv:
        return None

    executable = Path(argv[0]).name.lower()
    if executable in {"python", "python.exe", "python3", "python3.exe"}:
        if "-c" in argv or "-" in argv[1:]:
            return None
        if len(argv) >= 3 and argv[1] == "-m":
            module = argv[2]
            if not module.startswith("skills.") or module in BLOCKED_MODULES:
                return None
            return argv
        if len(argv) < 2:
            return argv
        script = (REPO / argv[1]).resolve()
        if REPO not in script.parents or script.suffix.lower() != ".py":
            return None
        if script in BLOCKED_SCRIPTS:
            return None
        return argv

    if executable in {"botte", "botte.exe"}:
        return argv if len(argv) >= 2 and argv[1] in SAFE_BOTTE_COMMANDS else None
    return None


def command_timeout(argv: list[str]) -> int:
    """Keep a bounded repository-scan allowance separate from ordinary smokes."""
    executable = Path(argv[0]).name.lower()
    if (argv[1:3] == ["-m", "skills.checkup.cli"] or
            executable in {"botte", "botte.exe"} and argv[1:2] == ["checkup"]):
        return CHECKUP_TIMEOUT
    return TIMEOUT


def main():
    readme = REPO / "README.md"
    if not readme.exists():
        print("README.md not found")
        return 0

    passed = failed = skipped = 0
    declared_match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (REPO / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    declared = declared_match.group(1) if declared_match else None
    public_readmes = [readme, REPO / "README.fr.md"]
    badge = f"version-{declared}-" if declared else ""
    mismatched_readmes = [
        path.name for path in public_readmes
        if badge not in path.read_text(encoding="utf-8")
    ]
    if declared == __version__ and not mismatched_readmes:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL version metadata: package={__version__}, pyproject={declared}")
        for name in mismatched_readmes:
            print(f"    {name}: expected version badge {badge!r}")

    commands = extract_commands(readme)
    for cmd in commands:
        if any(marker in cmd for marker in ("/path/", "<host>", "~/", "C:\\project-")):
            skipped += 1
            continue
        argv = safe_argv(cmd)
        if argv is None:
            skipped += 1
            continue
        deadline = command_timeout(argv)
        try:
            r = subprocess.run(argv, shell=False, cwd=REPO, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=deadline,
                               env={**os.environ, "PYTHONPATH": str(REPO)})
            if r.returncode == 0:
                passed += 1
            else:
                failed += 1
                print(f"  FAIL {cmd[:80]} (exit={r.returncode})")
        except Exception as exc:
            failed += 1
            detail = type(exc).__name__
            if isinstance(exc, subprocess.TimeoutExpired):
                detail += f", timeout={exc.timeout}s"
            # Keep command failures actionable without printing captured output,
            # environment values or arbitrary exception messages.
            if isinstance(exc, subprocess.TimeoutExpired):
                print(f"  TIMEOUT after {deadline}s  {cmd[:80]} ({detail})")
            else:
                print(f"  ERR ({detail})  {cmd[:80]}")

    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
