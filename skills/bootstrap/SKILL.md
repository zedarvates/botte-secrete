---
name: bootstrap
description: Configure Botte Secrète in a project with MCP wiring, shared Parcimonia and prefer-local guidance, optional AGENTS.md creation and a setup report. Use to install Botte, onboard a repository or diagnose missing project instructions. Configuration alone does not prove routing, model availability or cost savings.
---

# bootstrap — configure a project

Configure the installed toolkit for a project. For a new Codex project, include
`--create-agents-md` so its project-level instructions have an entry point.

```bash
python -m skills.bootstrap.cli /path/to/project
python -m skills.bootstrap.cli /path/to/project --create-agents-md
python -m skills.bootstrap.cli /path/to/project --scan-subnet --json
```

## What changes

1. Probe local backend ports and model endpoints, then replace the toolkit's
   `configs/llm-endpoints.json`. `--scan-subnet` extends probes to the local /24.
2. Merge the `botte-llm` entry into the project's `.mcp.json`. If an OculiX MCP
   jar is detected, also register its Java command. Registration does not start
   these servers; the consuming agent controls that later step.
3. Audit directives. `--create-agents-md` creates a missing `AGENTS.md`; when
   `CLAUDE.md` exists, the new file points to it instead of replacing its
   instructions. Independently of that flag, setup can append a policy pointer
   to an existing `AGENTS.md` or `CLAUDE.md`.
4. Replace `.botte/config.json` with detected backend/model, cloud-key **names**
   that are present, and default routing/budget values. Existing custom values
   are not merged. Key values are not copied into this report.
5. Create `.botte/policy.md` if absent and add a `UserPromptSubmit` preflight
   hook to `.claude/settings.json` if its marker is absent. New hooks pin the
   interpreter and script path from this installation, so another editable
   checkout cannot silently supply older guidance.
6. Replace `.botte/setup-report.json` and print next steps. Configuration and
   reports contain machine paths and backend metadata.

## Before running and retrying

Read [effects.json](effects.json) and match its project and probe scope to the
current task authorization. Preserve the prior versions of files that setup
will replace or modify. Check that existing MCP/settings JSON is readable and
has the expected object structure: the current implementation can replace
invalid JSON with defaults, while incompatible structures can fail midway.

Repeated setup updates the named entries, but is not a transaction or a general
safe retry. It can overwrite custom configuration and leave earlier writes
after a later failure. Inspect actual files after an interruption; restore
specific prior values where needed before rerunning. The tool supplies no
automatic rollback. Do not delete unrelated MCP servers or hooks during recovery.

The host receives guidance for assessing substantive work with Parcimonia,
reusing plans and choosing local mechanisms when sufficient. It must load its
supported instructions and tools, then execute and verify the task. Setup does
not prove assessment, automatic routing or savings.

Hook wiring targets Claude Code, not Codex or a global hook. Existing custom
policies and hooks are retained, including legacy module-based hooks; review
their migration explicitly. `--create-agents-md` never overwrites an existing
`AGENTS.md`.

## Verify and reuse

Compare changed files with their prior state, parse both JSON configurations,
and check the hook, policy pointer and chosen backend. A setup report is evidence
of completed setup steps, not proof of subsequent routing or token savings.
Restart the consuming agent when appropriate and verify its behavior on an
authorized small task; record actual results and remaining uncertainty.

Keep `.botte/policy.md` committed with the project. MCP, runtime config, hook
commands and setup reports can hold machine-specific paths; configure those on
each machine rather than committing generated endpoints or credentials.

For another project, reassess directives, machine paths, network scope and
existing customization. The reuse candidate in the sidecar requires target
validation. See the [common contract](../../docs/capability-effects.md).
