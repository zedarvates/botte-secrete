---
name: bootstrap
description: Configure Botte Secrète in a target project by discovering local backends, wiring MCP tools and a preflight hook, auditing directives, and writing routing configuration. Use when installing the toolkit or onboarding a project to local-first routing.
---

# bootstrap — configure a project

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
3. Audit directives. `--create-agents-md` can create a starter `AGENTS.md` if
   instructions are absent. Independently of that flag, setup can append a
   policy pointer to an existing `AGENTS.md` or `CLAUDE.md`.
4. Replace `.botte/config.json` with detected backend/model, cloud-key **names**
   that are present, and default routing/budget values. Existing custom values
   are not merged. Key values are not copied into this report.
5. Create `.botte/policy.md` if absent and add a `UserPromptSubmit` preflight
   hook to `.claude/settings.json` if its marker is absent.
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

## Verify and reuse

Compare the changed files with their prior state, parse both JSON configurations,
and check the hook, policy pointer and chosen backend. A setup report is evidence
of completed setup steps, not proof of subsequent routing or token savings.
Restart the consuming agent when appropriate and verify its behavior on an
authorized small task; record actual results and remaining uncertainty.

For another project, reassess directives, machine paths, network scope and
existing customization. The reuse candidate in the sidecar requires target
validation. See the [common contract](../../docs/capability-effects.md).

Related: [[llm_mcp]], [[auto_router]], [[preflight]], [[skill_finder]],
[[directives_audit]], [[llm_backends]].
