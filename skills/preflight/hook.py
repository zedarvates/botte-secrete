#!/usr/bin/env python3
"""Preflight hook — emits workflow guidance and suggested skills for Claude Code.

When wired, runs on each prompt before the host model sees it. The hook performs
no assessment, network request or LLM call. Emitted context still costs host
resources; the host remains responsible for following the guidance.

Designed for Claude Code's `UserPromptSubmit` hook (reads JSON on stdin, prints
context to stdout), but works standalone: pipe a prompt on stdin and it prints
the same guidance. Fast (lexical skill search, no LLM call) and crash-proof — a
hook must never block the user, so any error just yields no extra context.

Wire it (the deployer does this automatically) in .claude/settings.json:
    {"hooks": {"UserPromptSubmit": [{"hooks": [
      {"type": "command", "command": "python -m skills.preflight.hook"}]}]}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BOTTE_ROOT = Path(__file__).resolve().parents[2]
# The absolute script entry must prefer its own installation, even when the
# caller's PYTHONPATH already lists it after a different checkout.
sys.path.insert(0, str(BOTTE_ROOT))

from skills.preflight.policy import PARCIMONIA_GUIDANCE


def _read_input() -> tuple[str, Path]:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    prompt, cwd = "", Path.cwd()
    raw = raw.strip()
    if raw:
        try:
            data = json.loads(raw)
            prompt = data.get("prompt", "")
            cwd = Path(data.get("cwd") or ".")
        except (json.JSONDecodeError, ValueError):
            prompt = raw  # plain prompt on stdin
    return prompt, cwd


def _suggested_skills(prompt: str, project: Path) -> list[str]:
    try:
        from skills.skill_finder import find
        roots = [BOTTE_ROOT / "skills"]
        for extra in (project / ".claude" / "skills", project / "skills"):
            if extra.exists():
                roots.append(extra)
        res = find(prompt, roots=roots, top_k=3)
        return [m["name"] for m in res["matches"]]
    except Exception:
        return []


def build_context(prompt: str, project: Path) -> str:
    lines = [
        "[botte preflight] Read the project's .botte/policy.md when present; "
        "the following is workflow guidance, not a completed assessment.",
        PARCIMONIA_GUIDANCE.rstrip(),
        "[botte preflight] Prefer LOCAL for cheap work (classification/extraction/"
        "summaries/tool-choice) via local_chat·auto_route·find_skills = 0 cloud "
        "tokens; escalate only hard reasoning. Use `rtk <cmd>` in the terminal.",
    ]
    skills = _suggested_skills(prompt, project)
    if skills:
        lines.append("Relevant skills (local match): " + ", ".join(skills))
    # Nudge prompt-improvement only for big/ambiguous requests (keeps it cheap).
    if len(prompt.split()) > 40 or any(w in prompt.lower() for w in
                                       ("checkup", "audit", "refactor", "design", "improve")):
        lines.append("Big/ambiguous request → consider `improve_prompt` first.")
    return "\n".join(lines)


def main() -> int:
    try:
        prompt, cwd = _read_input()
        if not prompt:
            return 0
        ctx = build_context(prompt, cwd)
        # Claude Code injects stdout into context on UserPromptSubmit (exit 0).
        sys.stdout.write(ctx + "\n")
    except Exception:
        # Never block the user's prompt because of the hook.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
