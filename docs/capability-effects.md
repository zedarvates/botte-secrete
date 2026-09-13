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

The shared [effect-review skill](../skills/effect-review/SKILL.md) contains the
before/after method and target-context reuse assessment. Keep that procedure in
one place; individual skills retain their operation-specific facts and limits.

This migration adds capability declarations, authoring support and optional
planning/execution-report context. It does not change command classification,
permissions, scoring or learning. Do not
insert these fields into strict mission/handoff v1 objects: attach a reference
where their schema permits it, or introduce an explicit schema migration.

## Compact shared review

```bash
python -m skills.conductor.cli "audit my project" --review-effects --json
python -m skills.conductor.cli "audit my project" --execute --dry-run --review-effects --json --save both
```

`plan(..., review_effects=True)` inspects selected sidecars once, returning a
compact `review_before` for each step and one shared `review_method` reference.
`execute()` carries those cues by position and adds `review_after` from the result
and any retained observation companion. `run_goal(..., review_effects=True)`
connects both stages. MCP `conduct` and `execute_plan` expose `review_effects`.
All defaults remain unchanged. The shared method guides the consuming agent;
the code emits deterministic cues without invoking another model or executing
the method's instructions. It does not automatically load the skill into an LLM.

| Field | Meaning and limit |
|---|---|
| `review_before.source` | Actual selected `SKILL.md` path; its sibling `effects.json` holds the deferred detail. Names are not used to associate homonyms. |
| `declaration`, `capability_id`, `declaration_sha256` | Inspector status, independently resolved identity when available, and canonical JSON digest of that planning declaration. The digest is not the raw sidecar file hash or an execution lock. |
| `reversibility`, `retry`, `detail_counts` | Capability-wide labels and counts. They do not establish the consequences of one command or transfer reuse validation. |
| `attention`, `operation_assessment` | Structural review cues; operation assessment remains `deferred`. No cue means no listed structural signal, not permission or verified suitability. |
| `review_after.coverage`, `task_outcome` | `not_run`, `not_observed`, `partial` or `invalid_evidence` coverage; task outcome stays `unverified` for executed steps or conflicting/invalid evidence. |
| `observed_counts`, `evidence_ref` | Nonzero counts from a validated observation companion; omitted counts are zero within that partial report. The reference points to the same step's `effects_observed`. |
| `review_after.run_id`, `evidence_sha256` | Run identity and canonical digest of the validated companion, for subsequent targeted reads. They do not bind other execution-report fields or authenticate the evidence. |
| `declaration_changed` | Comparison with all observed calls matching the planning identity: any changed digest/status gives true; no match gives null. |
| `attention`, `next_action` after execution | Keep process failures, nested failures, unfinished calls/network attempts, write deviations, unknown facets and collection problems visible. Suggested next actions are advisory. |

The v1 sidecars describe operations in prose. The compact projector does not
guess operation matches from keywords, copy every effect into the plan or claim
that omitted prose is irrelevant. Read the selected operation's prerequisites,
scope and verification/recovery details when needed using the shared method.
An `execute(..., review_effects=True)` call on a supplied plan with neither cues
nor a declaration records `not_inspected`; it never invents a source from a name
or opens a path from that plan. Supplied plans and snapshots remain caller data.

`--review-effects` alone starts no observer. With execution it summarizes process
results, leaving actual effects unobserved. Add `--effects` for complete planning
declarations or `--execute --observe-effects` for the existing full evidence mode;
these explicit options can increase context substantially. A nonzero exit or
interrupted observation suggests checking state before retry; a zero exit or
HTTP response never establishes complete task success or validated reuse.
The compact review changes no execution gates, dependencies or retry behavior.

Direct results and saved overviews use the same bounded companion validation and
process reconciliation. Malformed, non-serializable or over-2-MiB companions give
`invalid_evidence`, an unverified outcome and no evidence reference, including
for steps reported blocked/skipped. Conflicting process status, exit code or
activity in a supposedly unexecuted step gives `process_evidence_mismatch` while
retaining valid evidence. Both cases suggest inspecting state before retrying.
An interrupted or failed attempt can have completed effects: check current
outputs and still-active work, retain verified completed results, and reassess
the remaining actions and their prerequisites before resuming.

`--review-effects --save` saves the returned compact report as JSON alongside the
requested Markdown/HTML. Add `--effects` when the handoff must preserve complete
planning declarations: a compact-only digest/reference cannot recover deleted
or changed source prose. Observation mode retains its full companion as before.
Neither source paths nor digests authenticate the caller or evidence.

Measure three planning examples with `python scripts/measure_effect_review.py`.
It reports ordinary, full-declaration and compact JSON UTF-8 byte sizes, including
the shared skill once per workflow and the overhead compared to ordinary output.
It also includes a fixed recovery-detail example, requesting prerequisites, task
scope and retry conditions for each declared selected skill, including the new
tool schema once and the serialized requests/responses. These fields are chosen
for a cost example, not automatically judged sufficient for a real operation.
This measures serialized context only. Other detail reads add cost; model tokens,
real task quality, execution overhead and general savings are not measured.
Further blanket declaration rollout is paused in favor of this shared method and
evaluation on concrete operations. Existing declarations remain available.

### Read deferred details

```bash
python -m skills.capabilities.cli effects skills/checkup --select /retry
python -m skills.capabilities.cli effects skills/checkup --select /preconditions --select /expected_effects/0 --expect-sha256 DIGEST_FROM_REVIEW
```

Python: `skills.capabilities.review.read_details(skill_dir, selectors,
expected_id=None, expected_sha256=None)`. MCP: discover `effect_details` with
`find_tool`, then pass the review's `source`, explicit `selectors` and its
`declaration_sha256` as `expected_sha256`. It stays outside the always-listed
core tools. MCP accepts canonical bundled `skills/<...>/SKILL.md` paths only;
absolute paths, traversal and directory aliases are rejected. Python/CLI support
external trees with the caller's independently supplied `expected_id` / `--id`.
The MCP caller cannot replace that identity with a sidecar claim.

Selectors name whole sections: `/preconditions`, `/expected_effects`,
`/downstream_effects`, `/reversibility`, `/retry`, `/required_scope`, `/analysis`
or `/reuse`. For the four list sections, `/section/0` selects a zero-based entry.
An effect entry retains all its scope, likelihood, basis, impact and verification
fields; a reuse entry retains its target context and evidence. No substring
matching, arbitrary nested fields or wildcards are implemented. Request 1–16
selectors; duplicate selectors are collapsed. Invalid selectors/digests fail
before declaration inspection. Whole sections can still be large.

The tool reads and validates the full bounded declaration and its source bindings
locally, then returns only the requested values under `selected`. It reduces
returned context, not those filesystem reads. The response also includes the
current inspector `status`, identity, canonical digest, `matches_expected` and
`error_count`. It does not execute evidence/verification text or perform inference.

| `selection_status` | Returned detail |
|---|---|
| `selected` | Every requested value, unchanged. An empty list remains an available empty section, not evidence that no effects exist. |
| `changed` | No fragments: the supplied digest differs from the current declaration. Obtain a fresh review and reassess; do not silently drop the expected digest to combine revisions. |
| `unavailable` | No fragments: missing, invalid or stale declaration. Use the ordinary full inspector/source for diagnosis; a matching declaration digest cannot make changed source files current. |
| `not_found` | No fragments: at least one list index is absent. `missing_selectors` identifies them; no partial selection is presented as complete. |

Without an expected digest, `matches_expected` is null: this is an initial current
read, with no comparison to a prior review. Missing/invalid declarations also
leave that comparison unknown. Canonical JSON digests ignore formatting and key
order; array positions and changed content affect them. The digest is neither a
raw-file hash nor an authenticated or immutable execution snapshot. CLI exits 0
only for `selected`, 1 for unavailable/changed/not-found selections, and 2 for
invalid arguments. The legacy `effects <skill_dir>` output remains unchanged.

Selected fragments do not verify applicability, task outcomes or authorization.
They do not identify relevant operations automatically or replace the selected
skill's complete instructions. Revalidate references across calls if the source
changes; only explicitly bound source files are checked, with the existing
snapshot/concurrency limits.

### Read retained evidence

```bash
python -m skills.capabilities.cli evidence .botte/reports/execution-effects-example.json --result 0
python -m skills.capabilities.cli evidence .botte/reports/execution-effects-example.json --result 0 --select /observations/o1 --select /network/n1 --expect-sha256 DIGEST_FROM_REVIEW_OR_INDEX
```

Use an actual JSON path returned by Conductor `--execute --observe-effects --save`;
the example filename above is a placeholder. Add `--review-effects` to retain the
compact review and its companion digest. `--result` is the zero-based position in
`results`, not the step's display order or capability name. A saved execution
requires this explicit position, even if it has only one result. For a standalone
v1/v2 observation companion, omit `--result`. No new report is saved by a read.
New Conductor saves return `effects_json` as a canonical project-relative path,
independently of the temporary-file helper's path format. Resolve it against the
execution working directory; MCP must use that same working directory. Older
absolute references still work in Python/CLI and require an explicit relative
path for MCP. The destination and unique/atomic JSON write behavior are unchanged.

Python `skills.capabilities.evidence.select_evidence(report, selectors=None,
expected_sha256=None)` projects a supplied companion without I/O. `read_evidence`
takes a `Path`, the same options and optional `result_index`. MCP `effect_evidence`
uses `source`, `selectors`, `result_index` and `expected_sha256`; discover it through
`find_tool`. It stays outside the always-listed core. MCP sources are canonical
`.botte/reports/<file>.json` paths relative to the server's working directory;
traversal, subdirectories, absolute paths and file/directory aliases are rejected.
CLI/Python can explicitly read other regular report files.

Omitting selectors returns `selection_status: indexed`: an ID index grouped by
call/network status and write comparison, plus retained declaration digests. Empty
groups mean no such records were collected, not that no effects occurred. v1 has
no network collection, so that index group is absent. Explicit selectors use
record IDs, **not array indexes**:

| Selector | Returned value |
|---|---|
| `/calls/c1` | Complete recorded call; ancestors are included under `linked_calls`. |
| `/observations/o1` | Complete write sample/comparison, with its call and ancestors. |
| `/network/n1` | Complete transport record, with its call and ancestors. HTTP 202 still leaves `remote_effects: unknown`. |
| `/declarations/DIGEST` | Complete declaration retained in this run, including its historical conditions and verification text. |

Use the actual IDs/digests from the index or linked call. For opaque IDs containing
`~` or `/`, escape them as `~0` or `~1`. Request 1–16 selectors; duplicates collapse.
No wildcards, nested field extraction or automatic selection of relevant effects
is implemented. Every successful view preserves the run context, process state,
problems, limitations and whole-companion summary, even if the chosen record
succeeded while another call failed. Selected values are unchanged detached
copies; `task_outcome` remains `unverified`. These views are projections, not
standalone observation companions accepted by `validate_report`.

Pass `review_after.evidence_sha256` or the initial index's `evidence_sha256` as
`expected_sha256`. A changed companion returns `changed` without fragments or an
index; a missing requested ID returns `not_found` without a partial selection.
Unreadable, malformed, oversized or absent evidence returns `unavailable` with a
reason. Invalid selectors/digests/result positions are rejected before document
reading. CLI exits 0 for `indexed`/`selected`, 1 for other states and 2 for invalid
arguments. An omitted expected digest means an initial read, not a comparison.

The entire selected companion is validated, including declaration digests and call
links, before projection. Its canonical digest ignores JSON formatting/key order
but changes with run identity, records or limits. Reordered execution results
therefore cannot silently substitute another run when the digest is supplied.
The digest binds only the companion: other wrapper fields, current resources,
source freshness and the author's identity are outside this check. Retained
declarations remain historical; this reader does not reinspect today's sources.

Reads are bounded to a 16 MiB document and a 2 MiB canonical companion. Special
files, duplicate JSON keys, non-finite numbers and observed file changes during
reading are rejected. Full local parsing/validation still occurs; index size,
linked ancestors, retained declarations and run limits can themselves be large.
Recorded resource paths, URLs, source paths and verification text are never opened
or executed. File checks are not a lock against concurrent writers or an attestation.
Existing execution output and saving behavior remain unchanged: targeted reads
help later review of already retained evidence, not the initial execution payload.

`python scripts/measure_effect_evidence.py` compares two explicitly synthetic
reports (2 and 64 writes) using real in-process MCP reads: one index and one
selection of the failed write, HTTP record and retained declaration. It includes
linked calls, run limits, requests/responses, the tool schema and the common
method. The raw-full baseline has no retrieval overhead. Short reports can cost
less to read whole; use targeted reads when their deferred detail justifies the
extra exchange. These examples measure serialized bytes, not model tokens, task
quality, runtime savings or a general cost threshold.

### Review a saved execution

```bash
python -m skills.capabilities.cli evidence .botte/reports/execution-effects-example.json --overview
```

Python `read_evidence(path, overview=True)` and MCP `effect_evidence` with `source`
and `overview: true` return all result positions, commands, process statuses and
freshly computed after-review cues. This explicit mode cannot combine with
`result_index`/`--result`, selectors or `expected_sha256`; mixed requests fail
before reading. Normal reads still require a position for execution reports.

The overview preserves repeated names and display orders by using actual array
positions. It checks the goal, mode, each result's status/exit-code fields and the
aggregate counts; malformed or inconsistent metadata returns `unavailable`
without silently dropping steps. It accepts at most 128 results in the existing
16 MiB document bound. Missing observation stays `not_observed` (or reported
`not_run` for blocked/skipped steps). Invalid or oversized companions remain
`invalid_evidence` in their own row, with an unverified outcome and no evidence
reference, while other rows remain visible.

Stored `review_after` verdicts are ignored. Cues are recomputed using the common
review helper; valid companions remain partial evidence. A conflict between the
step's process status and its observation is marked `process_evidence_mismatch`,
with an unverified outcome and a suggestion to inspect state before retrying.
When stored compact planning cues exist, their identity/digest/status support the
existing declaration comparison; otherwise that comparison stays unknown.
Those planning cues and all report metadata remain caller-supplied claims.

Each available `review_after.evidence_ref` contains read arguments: `source`,
`result_index` and `expected_sha256`. Pass this object to MCP `effect_evidence`
without `overview`, or to `read_saved_evidence`, for an index; add selectors to
retrieve records. Replaced or reordered companions cannot silently satisfy an
old reference with a different digest. Python/CLI references to external files
retain that explicit path and are not automatically made MCP-compatible.

`document_sha256` describes the canonical whole execution document, including
deferred fields; compare it separately if wrapper metadata changes matter.
The `expected_sha256` in each read reference still binds only its companion.
Neither digest authenticates a producer or locks the file. The overview defers
stdout tails, planning prose, observation records and detailed run limits to the
retained document and targeted reads. It creates no new journal, launches no
command and provides no automatic retry or dependency enforcement. CLI exit 0
means the overview was read successfully, even if it contains failed steps.

The evidence measurement script also covers the complete overview → index →
selection exchange for three-step synthetic executions, counting all requests,
responses, method and tool schema. Overview context and further reads add cost;
directly reading a short report can still be cheaper.

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
