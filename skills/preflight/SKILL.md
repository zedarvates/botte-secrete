---
name: preflight
description: Deliver shared Parcimonia instructions through a committed project policy and selective local assessment in Claude Code's UserPromptSubmit hook. Use for onboarding contributors, configuring a local project's agent guidance or diagnosing bypassed preflight instructions. This hook does not provide Codex or ChatGPT Work cloud lifecycle support.
---

# Selective Parcimonia preflight

Keep `.botte/policy.md` under version control and point project instructions to
it. Before substantive work or a materially different phase, use `assess_task`
when available and useful, with the real task and a bounded inventory of offered
tools. Reuse a current assessment for homogeneous work; skip trivial direct
steps. A lexical proposal establishes neither capability nor authorization.

If a helper is absent, fails or abstains, note the limitation once and let the
host interpret the task and choose an available workflow. Preserve meaning,
constraints and permissions; never retry just to force a route. Prefer a
suitable deterministic tool or a local backend only after verifying availability.

```python
from skills.preflight import policy
policy.write_default(project)          # Preserves an existing policy.
policy.ensure_agents_pointer(project)  # Appends to existing agent instructions.
```

## Existing Claude Code hook

The hook calls `assess_task` locally. Supported work yields the proposed intent,
conditional workflow guidance and at most three skill-name hints. Recognized
mixed work yields an abstention for the host to interpret or split. Trivial,
unsupported and negated prompts add no context. Preserve the original prompt.

The hook makes no model or network call and executes no selected tool. Input is
limited to 64 KiB UTF-8, tasks to 16 KiB, and context to 1 KiB including the final
newline. Invalid input or internal failure exits successfully without context,
leaving the user's prompt unblocked. Context still contributes to host overhead;
measure the complete accepted workflow before claiming savings.

```sh
printf '%s' '{"prompt":"Rechercher les PR GitHub","cwd":"."}' | python -m skills.preflight.hook
```

For GitHub tasks, conditional guidance names scoped planning and evidence
summaries without executing reads. Deterministic statistics, exact file-copy
inspection and supplied local Markdown links keep their separate tool contracts.
Software and game test proposals still need qualified adapters and verification.

## Project onboarding

`python -m skills.bootstrap.cli <project> --create-agents-md` can create starter
agent instructions when requested, write the default policy and wire the
existing Claude Code hook. Existing custom policies, instructions and unrelated
settings are retained. Merge new guidance explicitly into older custom policies.

The generated command pins the interpreter and hook script to the configured
installation; it does not depend on the project's working directory. Existing
legacy module-based entries are retained for explicit migration review.

Automatic wiring targets Claude Code's `UserPromptSubmit` only. Codex and cloud
hosts use their supported skill/MCP mechanisms; do not infer an active global
hook. A package cannot guarantee that a host selects a skill on every task.
See [portable instructions](../../docs/parcimonia-workflow.md#portable-instructions).

Related: [[bootstrap]], [[skill_finder]], [[checkup]].
