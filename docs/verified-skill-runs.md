# Verified skill runs

Use an explicit execution plan when a workflow needs observable acceptance
conditions, dependencies or a durable point of resumption. Lexical Conductor
plans remain suggestions: layer order alone does not establish dependencies.

The existing `--observe-effects` mode records instrumented calls and write
attempts. This explicit-plan mode verifies declared file predicates and resumes
unstarted steps. Their schemas remain separate; `--plan` cannot be combined
with `--observe-effects` or `--save` in v1. Use `--checkpoint` to retain this
mode's complete JSON report.

`botte.skill-plan/v1` and `botte.skill-run/v1` are separate companions to
capability-effects and mission/handoff contracts. Their schemas are
[skill-plan](schemas/skill-plan.schema.json) and
[skill-run](schemas/skill-run.schema.json). The stdlib entry point is
`skills.conductor.verified.execute_verified`.

## Author and run a plan

Create a trusted plan for the actual project and operation. Read the selected
skill body to confirm applicability and commands; inspect dependencies when
they change the operation's scope. `context` identifies the tested toolchain or
environment revision. `source_hashes` binds relevant project-relative source
files with SHA-256; include implementation dependencies that matter. Empty
bindings are permitted and reported as unbound.

```json
{
  "schema": "botte.skill-plan/v1",
  "goal": "Check the metrics output for this project",
  "context": "project-toolchain-v1",
  "steps": [{
    "id": "inspect",
    "capability": "metrics",
    "command": "python -m skills.metrics.cli .",
    "local": true,
    "needs": [],
    "requires": [{"kind": "file_exists", "path": "README.md"}],
    "ensures": [],
    "observes": [],
    "source_hashes": {}
  }]
}
```

This minimal example intentionally has no output checks: a zero exit is
`unverified`. Supply meaningful `ensures` for the task before expecting
`verified` or making another step depend on it. File existence proves only
existence; a hash, text predicate or typed JSON value can establish a stronger
condition. A command's own claim of quality is not an independent quality test.

```bash
# Preview: validates and classifies, but does not read observations or write a checkpoint.
python -m skills.conductor.cli --plan task-plan.json --project .

# Execute commands within the existing task scope and retain a private checkpoint.
python -m skills.conductor.cli --plan task-plan.json --execute \
  --checkpoint .botte/skill-runs/task.json

# Also dispatch gated operations if the current task already authorizes them.
python -m skills.conductor.cli --plan task-plan.json --execute --confirm \
  --checkpoint .botte/skill-runs/task.json --resume
```

MCP exposes the same interface as `execute_verified_plan`: `plan`, `project`,
`dry_run` (default true), `confirm` (default false), `timeout`, `checkpoint`,
and `resume`. Python defaults to execution with existing classification gates.
Preview does not promise that runtime prerequisites will hold later.

## Evidence and dependency semantics

- `requires` are checked immediately before dispatch and again before reuse
  or dependent consumption.
- `ensures` are checked after dispatch, including a failed process. Verification
  requires exit zero, at least one passing postcondition, and matching bound
  sources before and after the command. An unknown observation never passes.
- `needs` names earlier step IDs. At consumption, each dependency must still
  have valid required inputs, verified outputs and matching bound sources. An unavailable dependency
  blocks its consumers while unrelated branches remain executable.
- `observes` lists additional files whose presence, byte length and SHA-256
  are recorded before and after. `ensures` paths are observed automatically.
  An empty change list means no observed change among those files.
- `effects_before` is optional descriptive data copied from planning. It does
  not supply checks, commands, permissions or observations.

Supported checks are `file_exists`, `file_absent`, `file_sha256` (`value`),
`text_contains` (`value`, UTF-8), and `json_equals` (`pointer`, `value`). JSON
pointers use RFC 6901 escaping; values are compared without equating `true`
with `1`. Paths stay within the selected project; symlinks, traversal and
non-regular files produce no positive evidence. Observation reads are limited
to 8 MiB per file; plans to 1 MiB and 100 steps. Checkpoints are limited to
32 MiB when read.

Reports contain hashes and byte counts, not raw subprocess output or file
contents. They still contain the goal, context, paths and optional declarations,
so store them privately under `.botte/`. `child_cost: null` means unmeasured,
not free. A report can be referenced through existing `evidence_refs`; it is
not automatically promoted into Quality Compass training or support data.

## Resumption and recovery

A checkpoint is saved atomically before dispatch and after each result. An
exclusive adjacent `.lock` file prevents two writers using that checkpoint.
Existing checkpoints require explicit `resume`; plan and project/context
fingerprints must match. The fingerprint includes the Python interpreter,
but does not automatically inventory installed packages or remote services.

On resume, completed results are rechecked; valid ones are reused without
repeating their command. Changed prerequisites invalidate dependent results.
In v1, `requires` must remain true for a result to be reused or consumed by a
dependent step, alongside its output checks and source hashes. Bind input data
with `file_sha256` when a changed input would invalidate the result. A condition
deliberately consumed by execution, such as `file_absent` before creation,
requires reconciliation and a new plan before reuse. Historical
`precondition_checks` describe dispatch; `resume_precondition_checks` and
`dependency_checks` record the latest reuse and dependency checks separately.
Only previously unstarted steps may execute. Started but failed, unverified,
interrupted or uncertain work remains unresolved and requires reconciliation:
inspect actual resources and any active child processes, then prepare the
remaining authorized work as a new explicit plan. Do not reset checkpoint
states to manufacture permission to retry. After a host crash, inspect whether
the recorded work is still active before removing its orphaned lock.

This is a cooperative single-writer checkpoint, not a fleet lease service,
transaction, authenticated proof store or subprocess sandbox. A command can
affect resources outside the declared observation set. File checks are bounded
snapshots; concurrent hostile filesystem mutation is outside this v1 contract.
Both plan and checkpoint must come from the trusted task controller. Existing
task authority must cover commands and observations. The `confirm` flag is an
execution switch; declarations and labels grant no authority. A capability
name alone cannot make a different command run unattended in this mode.

## Pilots and further work

Run `python -m skills.conductor.test_verified` for execution/resumption tests
and `python -m skills.conductor.test_verified_pilots` for the operation pilots:

1. Checkup: detect inherited registry creation through actual checkup/advisor
   code with fixture hardware/backend discovery and blocked network access.
2. Conductor: fail an intermediate artifact check, keep independent work
   executable, resume verified work without duplicate writes.
3. Prefix pruner: compare original and reduced fixture context, check retained
   instructions and record real state writes. Byte reductions are measured;
downstream model-answer quality remains unmeasured.

See the [initial validation record](validation/verified-skill-runs-2026-09-08.md)
for the tested environment, suite results and remaining coverage limits.

The next evolution should connect this evidence to the existing trajectory and
shared-memory work through references, then compare current/candidate skills
on held-out representative tasks. Measure completion, errors, retries, latency,
actual child costs and preservation of necessary context. Keep routing advice
advisory until those observations support promotion. The initial implementation
does not train models, start a new database or modify running homelab services.
