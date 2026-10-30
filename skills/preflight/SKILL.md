---
name: preflight
description: Deliver shared Parcimonia and prefer-local instructions through a committed project policy and a Claude Code UserPromptSubmit hook. Use for onboarding new contributors, keeping agent guidance consistent or diagnosing missing local-routing guidance. The hook injects instructions; the host performs assessment and execution.
---

# preflight — deliver shared workflow instructions

The gap this closes: the optimizations (local routing, prompt improvement, skill
search) are **opt-in**, so a fresh prompt — especially after an update or from
another dev/agent — can miss them. Ship explicit entry instructions and make
them visible through supported host mechanisms:

## 1. Committed policy (`.botte/policy.md`)
The shared source of truth every dev and agent reads: consult Parcimonia before
substantive work, default to local for cheap work, escalate hard reasoning,
improve big prompts, run `/checkup` after updates, budget. **Commit it** so
multi-dev / multi-agent stays consistent.

When `assess_task` is exposed, call it once for a substantive task or changed
phase, with the actual task and a small inventory of available tools. Reuse the
assessment for homogeneous batches, rather than every read. Reassess when the
goal, constraints, tools or failure evidence changes; skip trivial direct actions.
Before scoped GitHub/PR research, use `plan_github_research` when available,
then a real GitHub reader. If a helper is absent, fails or abstains, report that
once and choose an available workflow as host. Preserve meaning and permissions;
do not retry to force a route. Advisory plans prove neither execution nor savings.

```python
from skills.preflight import policy
policy.write_default(project)          # idempotent
policy.ensure_agents_pointer(project)  # links AGENTS.md/CLAUDE.md to it
```

## 2. Preflight hook (Claude Code prompts)
A `UserPromptSubmit` hook that, before the expensive model sees the prompt,
injects: the Parcimonia workflow guidance, the prefer-local rule, the top relevant
skills (lexical `find_skills`), and an `improve_prompt` nudge for big/ambiguous
requests. Errors are caught so the hook does not block the prompt. No LLM is
called by the hook; its emitted context still contributes to host overhead.

The hook emits guidance; it does not itself call `assess_task`, connect MCP,
start a model or prove that the host followed the plan. Do not report an
assessment as completed merely because this text appeared in the prompt.

```bash
echo '{"prompt":"classify these tickets","cwd":"."}' | python -m skills.preflight.hook
```

The deployer wires it into `.claude/settings.json` with absolute interpreter and
script paths. The generated command runs from the target project without relying
on a working-directory override or another installed `skills` package.

## Install
`python -m skills.bootstrap.cli <project> --create-agents-md` writes the policy, wires the hook and
points AGENTS.md at the policy — all non-destructively. Works in any harness with
a pre-prompt hook (Claude Code today); the hook script is standalone.

Automatic wiring here targets Claude Code's `UserPromptSubmit` only. For Codex,
use the committed `AGENTS.md` and the packaged Botte Secrete workflow skill;
do not infer a Codex/global hook is active. Existing custom policies are retained
by the bootstrap; review and merge new guidance explicitly for older projects.
Legacy module-based hook entries are retained too; review their migration
explicitly if they resolve an older installation.
See [portable instructions](../../docs/parcimonia-workflow.md#portable-instructions).

Related: [[bootstrap]] (installs this), [[checkup]] (the canonical audit),
[[skill_finder]], [[prompt_improver]], [[auto_router]].
