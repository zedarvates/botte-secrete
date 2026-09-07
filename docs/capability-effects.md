# Capability effects, analysis and reuse

An optional `effects.json` beside a skill's `SKILL.md` describes its anticipated
effects and possible reuse. It is a declaration for the next agent to assess
against the current task. It does not establish that a run succeeded or grant
permission to execute a command. Evidence references are data, never commands
to execute automatically.

## Author a declaration

```bash
python -m skills.capabilities.cli template skills/my_skill --id owner/repo:skills/my_skill
```

The command prints a draft to stdout and does not create or replace files.
Save the reviewed JSON as `skills/my_skill/effects.json`. Fill in the unknowns
from the implementation and available evidence; keep genuine unknowns explicit.
The generated draft makes no positive safety or reuse claims. Bind the relevant
implementation files as well as `SKILL.md` using their SHA-256 byte digests.
Increment `contract_version` when the declaration changes. Review changed
behavior before refreshing hashes; blindly rehashing does not renew evidence.

Use the [JSON schema](schemas/capability-effects.schema.json) for external
authoring tools. The stdlib validator is `validate_contract()` in
`skills.capabilities.effects`; `inspect_effects()` also checks source bindings.

| Field | Meaning |
|---|---|
| `schema` | `botte.capability-effects/v1`; unknown versions are rejected. |
| `capability_id` | Qualified identity such as `owner/repo:skills/name`; do not identify shared skills by basename alone. |
| `contract_version` | Version of this declaration, independent of the implementation version. |
| `source_hashes` | Relative skill-local paths mapped to SHA-256 digests; include `SKILL.md` and affected implementation entry points. |
| `preconditions` | Required inputs, environment, dependencies and limits. |
| `expected_effects` | Intended outputs and direct changes, with scope, likelihood, basis, impact and observable verification. Include data exposure and resource costs where applicable. |
| `downstream_effects` | Delayed or indirect effects, affected consumers, and propagation conditions, using the same structure. An empty array means no effects documented, not proof of absence. |
| `reversibility` | `read_only`, `reversible`, `partial`, `irreversible` or `unknown`; describe recovery and remaining effects. |
| `retry` | `idempotent`, `conditional`, `non_idempotent` or `unknown`; state the check before retry and when to stop. A timeout is not evidence of non-execution. |
| `required_scope` | Required task authorization and resource scope; this text does not supply either. |
| `analysis` | Short evidence-based assessment, uncertainties and evidence references. |
| `reuse` | Candidate use, causal rationale, adaptations, target validation, status, validated context and evidence. |

Likelihood is qualitative: `conditional` describes an expected effect under
specified conditions; `probable` needs a stated basis; `plausible` is a credible
scenario; `unknown` records insufficient information. These labels are not
measured probabilities. Observed evidence belongs in the basis or analysis,
with its environment and limits, rather than being generalized to every run.

A reuse candidate is `exploratory`, `adaptation_to_test`, or
`validated_in_context`. The last requires a non-empty `validated_context` and
at least one evidence reference; the validator does not verify their truth.
Neither validation nor authorization transfers automatically to a new context.
Do not invent a reuse candidate merely to fill the array; `[]` is valid.

## Discover and inspect

```bash
python -m skills.capabilities.cli list --json --effects
python -m skills.capabilities.cli effects skills/capabilities
```

The Python equivalent is `load(include_effects=True)`. Ordinary `load()`,
`list --json`, `map` and `curate` preserve their existing output and avoid
reading sidecars. Opt-in discovery adds an `effects` object:

| Status | Interpretation |
|---|---|
| `missing` | No declaration exists; effects are not assessed here. |
| `invalid` | The JSON, version or structure is invalid or cannot be read. |
| `stale` | At least one bound source changed, is unavailable or leaves the skill directory. |
| `declared` | The structure is valid and the listed hashes match. This includes well-formed drafts and does not mean safe, complete or behaviorally validated. |

The single-skill `effects` command returns exit code 0 only for `declared`,
otherwise 1. Discovery continues when individual declarations are unavailable.
Malformed contracts are excluded from the output; stale ones remain visible
with errors so an agent can review what changed.

Only explicitly listed source files are checked. Dependency versions, runtime
state, unlisted code and changed evidence are not tracked automatically. Source
files must stay inside the skill directory; the sidecar is limited to 64 KiB
and each bound source to 8 MiB. No network requests or verification commands
are run by the inspector. This is a snapshot, not a lock on later execution.

## Use in a task and hand off

The Conductor can include declarations in a plan:

```bash
python -m skills.conductor.cli "inspect verified outcome history" --effects --json
python -m skills.conductor.cli "inspect verified outcome history" --effects --execute --dry-run --json
```

`plan(..., include_effects=True)` inspects only the selected capabilities.
`run_goal(..., include_effects=True)` and `execute()` retain supplied declarations
as `effects_before` in each result, including skipped, blocked and failed steps.
These are planning snapshots, not observations or renewed source checks.
Classification and authorization do not depend on their content. A failed
execution returns a nonzero CLI exit code in both text and JSON modes.

The CLI's text view shows status; JSON retains the complete declaration.
With `--effects --save`, a complete JSON companion accompanies the abbreviated
Markdown/HTML reports. Treat all these outputs according to the task's data
scope before sharing them.

Before using a selected capability, inspect its declaration when available and
relate the relevant effects to the actual inputs, resources and existing task
authority. Resolve material uncertainty with a proportional check. A missing
declaration alone neither authorizes nor forbids an otherwise authorized task.

After execution, report the observed result separately from the prediction:
affected resources, partial or ongoing effects, evidence, deviations, remaining
uncertainties and the next action. Keep the analysis concise and supported by
observations. Assess each proposed reuse in its target context before promoting
its status. Use the existing run-report or handoff mechanism for these facts.

This migration adds capability declarations, authoring support and optional
planning/execution-report context. It does not change command classification,
permissions, scoring or learning. Do not
insert these fields into strict mission/handoff v1 objects: attach a reference
where their schema permits it, or introduce an explicit schema migration.
