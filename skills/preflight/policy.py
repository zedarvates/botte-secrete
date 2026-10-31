"""Project policy — the shared, committed source of truth every agent/dev reads.

The gap the policy closes: our optimizations are opt-in, so a fresh prompt (after
a component update, or from another dev/agent) bypasses them. A committed
`.botte/policy.md` makes the rules explicit and consistent across people and
agents. The local preflight hook can add bounded, task-specific guidance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

POLICY_REL = ".botte/policy.md"

PARCIMONIA_GUIDANCE = """\
## Parcimonia before substantive work
- Before a substantive task or a materially different phase, call `assess_task`
  if exposed by the connected Botte Secrete runtime. Supply the task and a small
  inventory of relevant tools actually available; inspect their real schemas.
- Reuse the assessment for a homogeneous batch. Reassess when the goal,
  constraints, available tools or failure evidence changes; skip trivial direct
  actions. Do not add an assessment before every file read or command.
- Before scoped GitHub/PR research, use `plan_github_research` when available,
  then execute the reads with a real GitHub tool. Keep revisions and read limits.
- If a helper is absent, fails or abstains, note the limitation once and let the
  host choose a suitable available workflow. Preserve the user's language,
  negations, constraints and permissions; do not retry merely to force a route.
- These helpers provide advisory plans, not execution or authorization. Verify
  actual results and count assessment overhead before claiming any savings.
"""

DEFAULT_POLICY = """\
# Botte Secrète — project policy (read every turn)

Shared rules for all agents and developers on this project. Keep cheap, keep local.

""" + PARCIMONIA_GUIDANCE + """

## Routing (cost)
- Use Parcimonia for the first assessment of work that needs research, tool
  selection, code changes or test planning, when `assess_task` is available.
  Reuse a current preflight assessment; skip extra calls for trivial requests
  and direct actions whose tool and scope are already clear.
- Treat lexical proposals as hints. Check the actual offered tool schema and
  prerequisites; an abstention returns interpretation to the host. Do not infer
  permission, risk, locality or a working local backend from prompt wording.
- For GitHub/PR research, prepare scoped reads with `plan_github_research`, use
  the connected GitHub reader, then `summarize_github_evidence` for bulky supplied
  results when useful. Retain source links, completeness and head/base revisions.
- Prefer deterministic helpers and verified cache reuse for cheap transformations.
  Use a local model only when its backend and task suitability are established.
  Keep genuine architecture, security and debugging reasoning with the host.
- No model call inside a helper does not imply zero host tokens or free compute.
  Measure the accepted workflow, including tool overhead, retries and fallback.
- Prefer `rtk <command>` when available for compact terminal output.

## Prompts
- Split or clarify ambiguous work using evidence and host judgment. Consider
  `improve_prompt` only when useful and available.

## Hygiene (drift)
- After a component update or before a checkup, run `/checkup` (or
  `python -m skills.checkup.cli .`) — directives + metrics + infra + drift.
- Keep `CLAUDE.md`/`AGENTS.md` under ~2000 tokens and free of stale path refs.

## Budget
- Daily token budget: 50000 (auto_router downgrades when exceeded).
"""

AGENTS_POINTER = (
    "\n## Botte Secrète policy\n"
    "Read `.botte/policy.md` before substantive work: use Parcimonia assessment "
    "when useful and available, reuse it for homogeneous batches, and follow "
    "the explicit fallback when a helper is absent or abstains. Verify tool "
    "prerequisites and evidence, and run `/checkup` after updates.\n"
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
