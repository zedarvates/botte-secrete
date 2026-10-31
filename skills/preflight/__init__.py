"""preflight — distribute shared project workflow instructions.

- policy.py: a committed `.botte/policy.md` (shared rules for all agents/devs).
- hook.py: a Claude Code UserPromptSubmit hook that emits shared guidance and
  suggested skills, without executing the proposed workflow.

Installed into a project by `skills.bootstrap` (writes policy, wires the hook,
points AGENTS.md at it).
"""

from skills.preflight import policy

__all__ = ["policy"]
