---
name: conductor
layer: DECIDE
description: Select and order Botte capabilities for a goal, preview their commands, or execute a trusted plan within existing task authority. Use explicit skill plans when local artifact checks, dependencies or checkpointed resumption are needed. Selection is local and lexical; inspect selected skill instructions to confirm applicability before execution.
---

# conductor — goal → ordered plan of capabilities

The router, generalised: not "which model tier?" but "given this **goal**, which
capabilities, in which order, and what stays local?". The planning API produces
data; the optional executor runs the selected commands.

```bash
python -m skills.conductor.cli "test my desktop app and report crashes"
python -m skills.conductor.cli "reduce token cost and deploy on my project" --json
python -m skills.conductor.cli "inspect verified outcome history" --effects --json

# Execute the plan (read-only steps run; mutating/cloud steps are gated):
python -m skills.conductor.cli "audit my project and report metrics" --execute
python -m skills.conductor.cli "..." --execute --dry-run      # preview, runs nothing
python -m skills.conductor.cli "..." --effects --execute --dry-run --json
python -m skills.conductor.cli "..." --execute --confirm      # also run gated steps
```

## How it plans

1. **Curate** — picks the capabilities relevant to the goal ([[capabilities]]
   curator, local lexical match, 0 tokens).
2. **Order** — sorts them by the system's layers (SENSE → DECIDE → ACT →
   REMEMBER → GOVERN → DEPLOY): understand → decide → act → remember.
3. **Annotate** — each step gets a concrete command, a local/cloud flag, and the
   reason it's there.
4. **Estimate** — the goal's effort tier ([[auto_router]]) tells you whether any
   step's reasoning will escalate to the cloud.

Selection and metadata association use the registry path, so homonymous skills
keep their own layer, local flag and effects. Built-in command hints apply only
to their canonical `skills/<name>/SKILL.md` entry. Other entries retain a
`see <actual path>` pointer, which the executor skips even with `--confirm`.

Output: an ordered list of steps, **0 cloud tokens** to produce. It composes the
module collection into a coherent plan per goal — the conductor of the system.

## Executing the plan

The plan can be *run*, not just read. The executor classifies every step:

- **safe** — read-only analysis (`directives_audit`, `metrics`, `infra_advisor`,
  `checkup`, `cluster`, `llm_backends`) → runs unattended, 0 cloud tokens.
- **gated** — mutates state, generates artifacts, or escalates to the cloud →
  runs only with `--confirm` / `confirm=true`.
- **needs_args** — the command still has an unfilled `<placeholder>` → never runs.

`--dry-run` classifies everything and runs nothing (a preview). A failing step
yields a non-zero exit so CI can react. The runner is injectable, so the
behaviour is fully unit-tested without spawning subprocesses.

## Consequences and handoff

Read [effects.json](effects.json) before selecting an execution mode. Planning
reads local declarations; `--save` writes reports, and `--execute` launches
commands whose effects depend on their capability and arguments. An allowlisted
"safe" classification is not proof of no network access or cache writes.

Use `--effects` or `plan(..., include_effects=True)` to attach declarations only
for selected capabilities. MCP `conduct` and `execute_plan` expose
`include_effects: true` too. Selected paths preserve the association even when
names repeat; only canonical paths receive built-in command hints.
Match their scope to the actual command and current task
authorization. The executor carries the original snapshot as `effects_before`
for comparison with results; it never uses a declaration to unlock a command.
The snapshot itself remains unchanged. Review source or context
changes before relying on it. JSON contains complete details; `--effects --save`
also writes a JSON companion because Markdown/HTML tables abbreviate values.

After execution, distinguish a zero process exit from verified task success.
Record actual changes, evidence, partial effects, deviations and the next
action in the task report. In legacy execution a failed step does not stop later steps, and a
timeout does not prove that no work happened. Inspect state before retrying;
do not replay already successful mutations blindly. The orchestration's
`cloud_tokens` value does not account for model calls made by child commands.

Treat reuse suggestions as candidates requiring a check in their target
context. See the [common contract](../../docs/capability-effects.md).

Use `--execute --observe-effects --json` (MCP `observe_effects: true`) to add
a separate versioned observation report and compare declaration freshness at
instrumented call entry. The first adapters link checkup/infra/backend/cluster
calls and sample registry/LRU writes. Follow parent IDs to assess inherited
effects; `effects_summary` counts each write once and retains swallowed failures
or unfinished calls. A supported write facet is only partial evidence; network
effects, task success and costs remain unverified. Dry-run provides no execution
evidence. Add `--save both` to retain the full execution JSON for handoff. Inspect
partial state before retrying after errors or timeout. See the common contract's
observation section for coverage and schema details.

## Explicit checks and checkpoints

For a workflow with required artifacts or resumption, read
[verified skill runs](../../docs/verified-skill-runs.md). Its separate
`botte.skill-plan/v1` lists commands, local pre/postcondition checks, bound
source files and explicit dependencies. The lexical plan's layer order does
not establish those dependencies. The CLI `--plan` and MCP
`execute_verified_plan` preview by default; Python exposes `execute_verified`.

This mode distinguishes process exits from verified local predicates, records
observed file changes, and blocks consumers of unavailable results. A private
checkpoint permits resuming unstarted work after rechecking inputs, successful
outputs and bound sources.
Started but unresolved work requires state reconciliation. Read the report's
coverage: file checks cannot establish all downstream effects or model quality.
Reference the report through existing handoff evidence fields; never equate a
report's `verified` status with an independently verified task-quality label.

When a shared memory endpoint is configured, use
[action-consequence memory](../../docs/action-consequence-memory.md) to recall
relevant episodes before an explicit plan and retain its observed consequences.
`execute_remembered_plan` previews by default and returns execution and memory
results separately. If execution completed but ingestion failed, retry capture
from the archived report. The memory's local-check assessment does not replace
the current plan's dependency gates or establish a causal claim.

Exposed via [[llm_mcp]] as `conduct` (plan) and `execute_plan` (plan + run safe
steps). Built on [[capabilities]], [[auto_router]]; pairs with the [[control_loop]]
(measure savings → adapt the routing).
