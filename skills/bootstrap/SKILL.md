---
name: bootstrap
description: Configure Botte Secrète in a project with MCP wiring, shared Parcimonia and prefer-local guidance, optional AGENTS.md creation and a setup report. Use to install Botte, onboard a repository or diagnose missing project instructions. Configuration alone does not prove routing, model availability or cost savings.
---

# bootstrap — deploy the toolkit into a project

Configure the installed toolkit for a project. For a new Codex project, include
`--create-agents-md` so its project-level instructions have an entry point.

## Run it

```bash
python -m skills.bootstrap.cli /path/to/project
python -m skills.bootstrap.cli /path/to/project --create-agents-md   # scaffold AGENTS.md if missing
python -m skills.bootstrap.cli /path/to/project --scan-subnet --json
```

## What it does (idempotent)

1. **Discover local backends** (`llm_backends`) so routing has somewhere to send work.
2. **Wire MCP** — merges the `botte-llm` server into the project's `.mcp.json`
   (non-destructive; keeps any existing servers). The project's agent then gains:
   `auto_route`, `local_chat`, `fusion`, `find_skills`, `audit_local_usage`,
   `route_task`, `discover_backends`, `list_models`.
3. **Audit directives** (`directives_audit`) — reports the CLAUDE.md/AGENTS.md
   health; with `--create-agents-md`, creates a missing `AGENTS.md`. If a
   `CLAUDE.md` exists, links it instead of replacing its instructions.
4. **Write `.botte/config.json`** — chosen local model, detected cloud keys,
   token budget, routing mode (`auto`).
5. **Write `.botte/setup-report.json`** + print a summary with next steps.
6. **Deliver shared instructions** — create `.botte/policy.md` if absent, link
   it from the instruction file and wire the Claude Code `UserPromptSubmit`
   hook. The new hook pins the interpreter and script path from this installation
   so another editable checkout cannot silently supply older guidance.

## Result

The host receives configuration and instructions for assessing substantive work
with Parcimonia, reusing plans and choosing local mechanisms when sufficient.
The host must load its supported instructions and tools, then execute and verify
the task. Setup does not prove assessment, automatic routing or savings.

Hook wiring targets Claude Code, not Codex or a global hook. Existing custom
policies and hooks are retained, including legacy module-based hooks; review
their migration explicitly. `--create-agents-md` is opt-in and never overwrites
an existing `AGENTS.md`.

Keep `.botte/policy.md` committed with the project. MCP, runtime config, hook
commands and setup reports can hold machine-specific paths; configure those on
each machine rather than committing generated endpoints or credentials.

Related: [[llm_mcp]] (the tools wired in), [[auto_router]], [[skill_finder]],
[[directives_audit]], [[llm_backends]].
