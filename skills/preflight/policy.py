"""Project policy — the shared, committed source of truth every agent/dev reads.

The gap the policy closes: our optimizations are opt-in, so a fresh prompt (after
a component update, or from another dev/agent) bypasses them. A committed
`.botte/policy.md` makes the rules explicit and consistent across people and
agents — the preflight hook injects it every turn so nobody has to remember.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

POLICY_REL = ".botte/policy.md"

DEFAULT_POLICY = """\
# Botte Secrète — project policy (read every turn)

Shared rules for all agents and developers on this project. Keep cheap, keep local.

## Routing (cost)
- **Default to LOCAL** for cheap/transformational work: classification,
  extraction, short summaries, translation, formatting, syntax checks, and
  **choosing which skills/tools to use**. Use the `botte-llm` MCP tools
  (`local_chat`, `auto_route`, `find_skills`) — these cost 0 cloud tokens.
- Escalate to the cloud model **only** for genuine reasoning: architecture,
  multi-file changes, security, debugging root-causes.
- Prefer `rtk <command>` for terminal commands (compact output).

## Prompts
- Before a big/ambiguous request, improve it locally (`improve_prompt`) so the
  cloud model starts from a structured, unambiguous prompt.

## Hygiene (drift)
- After a component update or before a checkup, run `/checkup` (or
  `python -m skills.checkup.cli .`) — directives + metrics + infra + drift.
- Keep `CLAUDE.md`/`AGENTS.md` under ~2000 tokens and free of stale path refs.

## Budget
- Daily token budget: 50000 (auto_router downgrades when exceeded).
"""

AGENTS_POINTER = (
    "\n## Botte Secrète policy\n"
    "This project follows `.botte/policy.md` (prefer local models for cheap work, "
    "improve prompts locally, run `/checkup` after updates). Read it.\n"
)


def policy_path(project: Path) -> Path:
    return Path(project) / POLICY_REL


def load(project: Path) -> str:
    """Return the project policy text, or the default if none is committed."""
    p = policy_path(project)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            pass
    return DEFAULT_POLICY


def write_default(project: Path, overwrite: bool = False) -> Optional[Path]:
    """Write `.botte/policy.md` (idempotent). Returns the path if written."""
    p = policy_path(project)
    if p.exists() and not overwrite:
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DEFAULT_POLICY, encoding="utf-8")
    return p


def ensure_agents_pointer(project: Path) -> bool:
    """Add a one-paragraph pointer to the policy into AGENTS.md/CLAUDE.md if missing.

    Returns True if a pointer was added.
    """
    for name in ("AGENTS.md", "CLAUDE.md"):
        f = Path(project) / name
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if ".botte/policy.md" in text:
            return False  # already references it
        try:
            f.write_text(text.rstrip() + "\n" + AGENTS_POINTER, encoding="utf-8")
            return True
        except OSError:
            return False
    return False
