"""preflight — make the optimizations automatic, not opt-in.

- policy.py: a committed `.botte/policy.md` (shared rules for all agents/devs).
- hook.py: a UserPromptSubmit hook that injects the policy + suggested skills +
  prefer-local nudge on every turn (0-cost, crash-proof).

Installed into a project by `skills.bootstrap` (writes policy, wires the hook,
points AGENTS.md at it).
"""

from skills.preflight import policy

__all__ = ["policy"]
