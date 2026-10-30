---
name: preflight
description: Add selective local Parcimonia task assessment to the existing Claude Code UserPromptSubmit hook and maintain the shared project policy. Use when a local project should assess supported work before choosing tools, or when repeated prompts bypass the configured guidance. This hook does not provide Codex or ChatGPT Work cloud lifecycle support.
---

# Selective Parcimonia preflight

Keep the shared `.botte/policy.md` under version control and point the project's
agent instructions to it. The policy guides the host; a tool recommendation
does not establish availability, permission or a verified result.

```python
from skills.preflight import policy
policy.write_default(project)          # Idempotent; preserves an existing policy.
policy.ensure_agents_pointer(project)
```

The existing Claude Code hook calls `assess_task` locally. For supported work it
emits the proposed intent, conditional workflow guidance and at most three
skill-name hints. A detected mixed workflow returns an abstention for the host
to interpret or split. Trivial, unsupported and negated requests add no context.
The host retains the original prompt and its constraints.

The hook makes no model or network call and executes no selected tool. Input is
limited to 64 KiB UTF-8, the task to 16 KiB, and emitted context to 1 KiB including
the final newline. Invalid input or an internal failure produces no context and
exits successfully so the user's prompt remains unblocked. These properties do
not establish zero host tokens, zero compute cost or measured savings.

```sh
printf '%s' '{"prompt":"Rechercher les PR GitHub","cwd":"."}' | python -m skills.preflight.hook
```

`python -m skills.bootstrap.cli <project>` can install the existing
`.claude/settings.json` entry without replacing unrelated settings:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [
  {"type": "command", "command": "python -m skills.preflight.hook"}]}]}}
```

This wiring targets Claude Code. Run the module standalone for a supported
local pre-prompt integration; do not add it to the public Codex plugin manifest
or claim that it runs in ChatGPT Work cloud. Codex and cloud hosts use their
supported skill/MCP guidance and must check the tools exposed by that session.

Related: [[bootstrap]], [[skill_finder]], [[checkup]].
