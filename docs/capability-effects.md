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
| `invalid` | The JSON, version, structure or identity is invalid, cannot be read, or cannot be resolved independently. |
| `stale` | At least one bound source changed, is unavailable or leaves the skill directory. |
| `declared` | The structure, resolved identity and listed hashes match. This includes well-formed drafts and does not mean safe, complete or behaviorally validated. |

The single-skill `effects` command returns exit code 0 only for `declared`,
otherwise 1. Discovery continues when individual declarations are unavailable.
Malformed contracts are excluded from the output; stale ones remain visible
with errors so an agent can review what changed.

Bundled identities are resolved from the actual path under this repository's
`skills/` tree, using `zedarvates/botte-secrete:<path>`. External trees require
the caller to supply the expected identity from its own trusted mapping:

```bash
python -m skills.capabilities.cli effects /path/to/other/skills/worker --id owner/repo:skills/worker
```

Use `inspect_effects(path, expected_id="owner/repo:skills/worker")` for one skill,
or `load(skills_root, include_effects=True, capability_namespace="owner/repo:skills")`
for a tree. Never derive the expected identity from the sidecar being checked.
Effects-aware discovery retains separate paths with identical folder basenames.
Use `load(..., preserve_paths=True)` to retain every path without inspecting
sidecars, then `curate(..., include_paths=True)` to carry the selected path.
The Conductor uses these paths to associate metadata in both planning modes;
matching names in different locations remain distinct. Legacy discovery retains
its historical basename deduplication. Paths identify catalog entries in this
snapshot, not immutable global identities.

The repository test discovers every present `effects.json`, including new and
nested declarations, and checks its identity and freshness. Missing declarations
remain a migration count, not a requirement to declare every capability at once.

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
The Conductor associates layers, local flags and effects by selected source path.
It uses built-in command hints only for their canonical skill paths; an entry
with the same display name elsewhere gets a non-runnable pointer to its source.
The MCP tools `conduct` and `execute_plan` accept the same optional
`include_effects: true`; omitted or false preserves their previous output.
`run_goal(..., include_effects=True)` and `execute()` retain supplied declarations
as `effects_before` in each result, including skipped, blocked and failed steps.
These remain planning snapshots. Use the separate observation mode below for
execution-time declaration checks and partial runtime evidence.
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

## Operation and dependency boundaries

In each effect, name the actual operation and flags in `effect`/`basis` and
the concrete resources in `scope`. A capability-wide `partial` reversibility
or `conditional` retry summary does not make every operation interchangeable.
For example, backend `list` reads, `audit --fresh` probes and overwrites the
registry, and `chat` discloses a prompt to the selected endpoint. Cluster
`status` may also update LRU state before any delegation occurs.

Record dependency conditions in `downstream_effects` and link relevant
declarations in the skill guidance. `checkup` calls `infra_advisor`, which may
refresh `llm_backends` on an empty registry. The parent source hashes do not
track those external implementations: inspect the dependency version used by
the target operation when this matters. References are not automatically
resolved, aggregated, or executed by the declaration inspector.

## Observe and reconcile a run

```bash
python -m skills.conductor.cli "audit my project" --execute --observe-effects --json --save both
```

`--observe-effects` requires execution mode and implies `--effects`. Python
`run_goal(..., observe_effects=True)` and MCP `execute_plan` with
`observe_effects: true` expose the same option. Dry-run and blocked steps produce
`not_run` records without launching an observer. Existing execution classification
and confirmation rules still apply.

Each result adds `effects_observed` using the separate
[`botte.effect-observations/v2` schema](schemas/effect-observations-v2.schema.json),
an `effects_summary`, and `effects_changed_since_plan` (true, false, or null when
no matching execution identity is available). The original `effects_before`
is retained. Each instrumented call re-inspects its declaration at entry;
the report deduplicates immutable declaration snapshots by SHA-256. It retains
the observer's UTC start time, working directory and Python version, and each
call's actual source directory, including when its declaration is unavailable. A changed
status or declaration is visible, but does not automatically block execution.
The v2 companion adds a required `network` array. Readers still accept existing
[closed v1 reports](schemas/effect-observations.schema.json); v1 producers and
stored artifacts need no rewriting. Consumers must select the declared version.
The separate capability-effects and mission/handoff schemas remain v1.

The adapters cover these actual calls, including explicitly enrolled discovery
workers:

| Capability | Recorded operations | Direct evidence |
|---|---|---|
| `checkup` | `run` | Inherited evidence through linked children |
| `infra_advisor` | `auto_audit`, `gather` | Inherited registry writes and probes |
| `llm_backends` | `audit`, `registry.refresh`, `registry.save`, `discover`, `scan_host`, `probe_host`, `chat`, `chat_json` | Registry writes, TCP connects, discovery GETs and model POSTs |
| `cluster` | `status`, `save_lru_state`, `delegate` | LRU writes, delegation POSTs and inherited discovery |

Supported CLI commands run in a child wrapper with a private temporary checkpoint.
Calls have unique IDs and parent IDs; each write or network attempt belongs to
one call, so a parent and its descendants do not inflate the counts. Follow the
registry write's call through `registry.refresh`, `gather`, `auto_audit` and
`checkup.run` to see the inherited consequence. A cached audit can record calls
without any write. That does not establish that all its effects were absent.

Each write records its attempted operation, absolute resource path, bounded
before/after file size and SHA-256, and a reference to one effect in the call's
declaration. No file contents, prompts, credentials, headers, response bodies,
exception strings or raw endpoint arguments are collected by this observer.
Paths, fingerprints and declarations can still be private; existing command-output
tails can contain separate sensitive data.

Write reconciliation checks only the `file_present_after_write` facet:
`supported` means a returned write and a present post-write sample with a current
declaration; `deviation` records a raised write or a missing post-write file;
`unknown` covers unavailable/stale declarations, unfinished writes and unreadable
samples. This never validates the whole prose effect or its preconditions.
Even identical samples retain the write attempt. Errors absorbed by a parent
remain visible in `failed_writes`; a successful parent does not erase them.

Network records describe the actual TCP connect or HTTP open/read attempt,
method, duration, categorical failure and received HTTP status. Targets use
opaque aliases scoped to this report, plus scheme and address kind. These
describe URL origins or supplied address literals, without DNS resolution;
they do not identify the actual peer, proxy, owner or authenticated principal.
For HTTP, the final response origin is compared with the requested origin;
intermediate redirects are not enumerated. Delegation rejects redirects even
when observation is disabled, so task credentials are not forwarded to another
endpoint. Discovery retains its existing GET redirect behavior.

`transport_response: supported` means a TCP connection returned or an HTTP
status was received, with a current declaration and bound effect reference.
An HTTP error response supports that narrow facet too. Missing/stale declarations,
unanswered connects and requests remain `unknown`. A received status does not
prove that the response body finished: `response_complete` records that separately.
`remote_effects` always remains `unknown`, including HTTP 200/202 replies and
`delegated: true`. Model JSON retries appear as distinct POST attempts, without
inferring token use, cost, answer quality or receiver-side task completion.

Checkpoints are flushed at call/write and network phase boundaries. After a
timeout, completed samples and received HTTP metadata remain available while
unfinished operations stay visible; the parent records
`timed_out`. Invalid, missing, oversized or mismatched-run checkpoints produce
unknown evidence. The summary recommends inspecting partial state before retry
when interruption, a failed write/call or an unfinished/failed POST is recorded.
Inspect receiver state after an uncertain POST; a caller timeout cannot establish
whether remote work already happened. The observer performs no rollback, probe,
retry or cancellation itself.
`--save` reserves a unique filename and atomically writes the complete execution
JSON beside abbreviated Markdown/HTML; concurrent saves do not replace another
JSON companion. An interrupted reservation can leave an empty file.
Reference that artifact through existing `evidence_refs`; do not extend strict
mission/handoff v1 objects with unsupported fields.

For direct Python integration, `ObservationSession` is an opt-in context manager
in `skills.capabilities.observations`. Inside it, instrumented functions retain
their normal return values. `session.report` and `summarize(session.report)` expose
the evidence. Its process remains `running` because the caller's process has not
exited. `validate_report()` checks v1/v2 structure, bound declarations, graph
references and evidence/comparison consistency without executing references or
networking. `submit_observed()` explicitly propagates the current context to
enrolled thread-pool work. Join those workers before closing the session for
complete instrumented coverage; closing freezes its report and checkpoint and
marks unfinished calls. Later worker completions cannot rewrite that evidence.

Coverage is cooperative and partial: there is no OS-wide tracing, remote-call
attestation, cost measurement, verified task success, or automatic discovery of
every downstream effect. Uninstrumented commands still execute normally and get
an explicit unknown-coverage report. An injected runner observes instrumented
calls in its context and explicitly enrolled workers. Other threads/processes
do not inherit the session automatically. Files above 8 MiB, non-regular files
and uncertain samples remain unknown; reports are bounded to 128 calls,
256 writes, 256 network attempts and 2 MiB for persisted checkpoints.
Exhausted limits are reported. Concurrency can affect file samples; evidence does
not prove exclusive causation. Checkpoints may miss an unfinished final write.
`unassessed_effects` counts all unique declared effects, including those with one
supported facet. No complete-effect verification or automatic reuse promotion is
performed. Inter-step dependency enforcement and transactional recovery remain
separate work.

## Initial rollout

The following declarations cover the initial capabilities. This is coverage
of reviewed source descriptions, not validation of every execution or reuse.
Run `list --json --effects` to see current coverage and source freshness.

| Capability | Effects distinguished in its declaration |
|---|---|
| `capabilities` | Discovery, inspection, output disclosure and downstream selection. |
| `conductor` | Planning, report saving, command execution and partial failures. |
| `events` | Append, rotation, export, clearing and best-effort logging. |
| `trajectory` | Advisory reads, outcome/support writes, legacy capture and partial persistence. |
| `bootstrap` | Backend probes, project configuration, hooks and later agent behavior. |
| `cache` | Freshness checks, eviction, cache writes, scan callbacks and approximate matches. |
| `checkup` | Project/host diagnostics, conditional probes, report saving and incomplete scan coverage. |
| `llm_backends` | Registry reads, discovery/probes, registry replacement and model requests. |
| `cluster` | Status/LRU writes, backend discovery and delegation. |
| `infra_advisor` | Host/project diagnostics and inherited discovery writes. |
| `preflight` | Prompt guidance, policy writes and effects on later agent sessions. |
| `prefix_pruner` | Context removal, retention counters, shared state writes and downstream information loss. |
| `prefix_tree` | Plaintext prefix persistence, comparison output and receiver-baseline assumptions. |
| `cardinal` | Scoped counter-review, input completeness, report-derived scoring and verdict persistence. |
| `report` | Rendering loss, collision-safe file creation, partial saves and output disclosure. |
| `auto_router` | Decision reads, inference/fusion disclosure, scoped cache reuse, estimated budgets and unverified telemetry. |
| `tiered_router` | Advisory tier estimates, in-memory accounting/cache mutations and partial context reconstruction. |
| `context_budget` | Catalog reads, lexical shortlisting, quantized costs and downstream instruction omissions. |
| `control_loop` | Telemetry append, heuristic proposals, validated threshold replacement and later routing changes. |
