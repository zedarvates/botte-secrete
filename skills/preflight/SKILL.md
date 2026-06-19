---
name: preflight
description: Make the token-saving optimizations automatic instead of opt-in — a committed project policy plus a UserPromptSubmit hook that injects the prefer-local rules and suggested skills on every prompt, so a fresh prompt (after a component update, or from another dev/agent) never bypasses local routing. Use when the user wants the prefer-local behaviour enforced automatically, consistency across multiple devs/agents, or asks why their prompts aren't using local models by default.
---

# preflight — enforce prefer-local, automatically

The gap this closes: the optimizations (local routing, prompt improvement, skill
search) are **opt-in**, so a fresh prompt — especially after an update or from
another dev/agent — bypasses them. Enforcement that doesn't depend on the model
remembering:

## 1. Committed policy (`.botte/policy.md`)
The shared source of truth every dev and agent reads: default to local for cheap
work, escalate only hard reasoning, improve big prompts, run `/checkup` after
updates, budget. **Commit it** so multi-dev / multi-agent stays consistent.

```python
from skills.preflight import policy
policy.write_default(project)          # idempotent
policy.ensure_agents_pointer(project)  # links AGENTS.md/CLAUDE.md to it
```

## 2. Preflight hook (every turn, ~0 cost)
A `UserPromptSubmit` hook that, before the expensive model sees the prompt,
injects: the prefer-local rule, the top relevant skills (lexical `find_skills`,
0 tokens), and an `improve_prompt` nudge for big/ambiguous requests. Crash-proof
(a hook must never block you) and fast (no LLM call).

```bash
echo '{"prompt":"classify these tickets","cwd":"."}' | python -m skills.preflight.hook
```

The deployer wires it automatically into `.claude/settings.json`:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [
  {"type": "command", "command": "python -m skills.preflight.hook"}]}]}}
```

## Install
`python -m skills.bootstrap.cli <project>` writes the policy, wires the hook and
points AGENTS.md at the policy — all non-destructively. Works in any harness with
a pre-prompt hook (Claude Code today); the hook script is standalone.

Related: [[bootstrap]] (installs this), [[checkup]] (the canonical audit),
[[skill_finder]], [[prompt_improver]], [[auto_router]].
