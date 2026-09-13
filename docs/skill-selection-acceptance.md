# Skill selection acceptance

The [protocol replay](skill-selection-review.md) proves that numbered replies
retain the intended paths. This acceptance runner measures the finder output
against operation-level oracles using the same configured local model on two
trusted Git checkouts. It composes the existing finder, `LocalLLMClient` and
[Conductor checkpoints](verified-skill-runs.md); it adds no runtime router.

The [starter corpus](examples/skill-selection-cases.json) contains twelve
synthetic situations: six applicable operations and six exclusions or missing
prerequisites. Three skills share the name `memory`. The corpus tests private
and project notes, RAM inspection, checkpoint inspection and image conversion.
These are fictional candidates; the runner never executes their operations.

## Choose the next operation

Use the current run state to choose the operation. The
[six-axis coverage review](tool-improvement-axes.md) maps these mechanisms to
their evidence and remaining limits. Read the linked procedure before using
its command.

| Situation | Operation and prerequisites | Output, effects and next decision |
| --- | --- | --- |
| A distinct comparison is being prepared | [Preview](#prepare-and-execute) with trusted baseline/candidate checkouts and a corpus. | In-memory plan and source hashes; no writes or inference. Review the candidate, cases and runtime configuration before execution. |
| A new comparison is ready to run | [Execute](#prepare-and-execute) with frozen sources/cases, explicit registry, backend, model, runtime identity and a new output directory. | Private manifest/checkpoint and up to 72 model calls; comparison and acceptance remain separate. Fictional operations are not executed. |
| A comparison was interrupted | [Resume](#read-the-evidence-and-resume) with the original inputs, output directory and checkpoint, after inspecting current process/server state. | Rechecks completed observations and dispatches only unstarted work. Started or uncertain calls require reconciliation; a completed refused run needs no new calls. |
| A retained comparison needs a decision | [Assess offline](#automated-acceptance-assessment) with its separately retained SHA-256 and bound corpus. | Recomputed results on stdout; no writes or model calls. Exit 3 identifies evidence gaps; exit 4 preserves the quality refusal. |
| An assessment should be retained in memory | [Export](#retain-an-assessment-in-shared-memory) with project, visibility and a fixed assessment timestamp; save the exact emitted JSON. | A capture request on stdout, with the quality exit retained. The existing authenticated Memory Hub client performs the separate write and supplies the receipt. Retry only the identical saved request after uncertain transport. |
| A recalled assessment may inform another task | [Review recall](#review-a-recalled-assessment-before-reuse) with a saved response, expected project, pinned comparison and caller-selected checkout. | Checks the supplied evidence and samples current sources without contacting a service. Incomplete recall or source drift returns 3; runtime, live service state and task prerequisites still need review. |

Neither a prepared request nor an offline review is a memory-service receipt.
Several assessments of one comparison remain one source of model evidence.
These operations do not authorize task execution or automatic promotion.

## Initial preparation

The [initial preparation record](validation/skill-selection-preparation-v1.json)
binds the starter corpus and harness to a preview with twelve cases and 24
planned calls, zero inference and no measured quality or cost. The candidate
was a working-tree snapshot at that time. The registered regression suite uses
injected replies and a loopback HTTP fixture, including actual child processes
and interrupted/resumed runs; it supplies no homelab or real-model evidence.

## First measured CPU pass

On 2026-09-10, one frozen pass made **24 real inference calls** with the existing
Qwen2.5-0.5B-Instruct Q8_0 weights and llama.cpp build 10809 on CPU. The baseline
was `6651335fa0d96a39d14f3b95c10d8a30763fc835`; the candidate was
`8f2bd6e7031785a294baa53bf642b73f994d3205`. Both source snapshots matched their
commits. The corpus, prompts and source code were unchanged during the run.
There were no corrective retries or inference warmup requests.

The [protocol frozen before execution](validation/skill-selection-cpu-protocol-v1.json)
records the source, corpus, harness, weight and runtime hashes, four CPU threads,
one slot, 4,096 context tokens and disabled prompt caching. The
[unmodified comparison](validation/skill-selection-cpu-v1.json) retains all 24
observations. The [execution and handoff record](validation/skill-selection-cpu-execution-v1.json)
adds per-case interpretation, resource consequences and the decision.

| Observed measure | Baseline | Candidate |
| --- | ---: | ---: |
| Exact selection with an available model review | 2/12 | 5/12 |
| Exact selection on applicable operations | 2/6 | 5/6 |
| Correct abstention on exclusions or missing prerequisites | 0/6 | 0/6 |
| Negative cases returning an unwanted selection | 6/6 | 6/6 |
| Extra returned paths across all cases | 12 | 6 |
| Required paths retrieved on positive cases | 6/6 | 6/6 |
| Endpoint-reported prompt tokens, total | 1,423 | 4,199 |
| Endpoint-reported completion tokens, total | 24 | 24 |
| HTTP round-trip median | 335 ms | 845 ms |
| HTTP round-trip p95 | 443 ms | 1,219 ms |

Three cases become exact: private notes, project decisions and RAM inspection.
Both versions still return a selection in **every** abstention-required case.
For the two-destination task, the baseline returns both required paths through
lexical fallback; that is not credited as a successful model review. The
candidate's reviewed selection returns only the private-note path. Thus raw
path equality alone would be 3/12 versus 5/12 and would conceal the baseline's
fallback. No previously exact reviewed selection is lost, but the loss of the
second destination remains an observed regression in returned coverage.

**Decision: do not promote this runtime for autonomous operation selection.**
All observations are complete, but exclusion handling fails and one multi-skill
request remains incomplete. Supplying full instructions and preserving identity
does not establish that the model applies prerequisites correctly. This
comparison changes instruction delivery, identity and abstention parsing
together; it does not isolate the cause of the three improvements.

This small synthetic pass supplies development evidence. Qualification still
requires separately frozen, independently reviewed target situations. The
prompt-token total is about 2.95 times larger for the candidate. Timings describe
this shared CPU host and a single pass; p95 over twelve calls is the maximum,
and the first prompt is cold. They establish no GPU performance or general
latency claim. Downstream task quality, energy and monetary cost remain unmeasured.

The checkpoint verified all 24 observations and their file hashes were rechecked.
Sources, weights and runtime files were unchanged after inference. The owned
loopback server exited successfully; no call is active, pending or uncertain,
and no selected operation was executed. This run is complete and must not be
replayed to improve its score. Its results were not promoted into learning
memory or an active routing rule. Subsequent evidence-only commits do not change
the revisions that were actually measured.

## Prepare and execute

From the candidate checkout, prepare a baseline worktree at the revision before
the selection correction. Use a new directory for each distinct comparison.

```bash
git worktree add ../selection-baseline 6651335fa0d96a39d14f3b95c10d8a30763fc835
python scripts/benchmark_skill_selection.py --baseline ../selection-baseline
```

Preview validates the corpus, hashes sources and constructs the plan in memory.
It writes nothing, discovers no endpoint and performs no inference. Execution
uses a saved registry and requires one unambiguous backend label, an explicit
advertised model tag and a runtime identity chosen by the operator. Copy the
following placeholders to match the authorized local configuration:

```bash
python scripts/benchmark_skill_selection.py --baseline ../selection-baseline \
  --registry configs/llm-endpoints.json --backend "YOUR_BACKEND_LABEL" \
  --model "YOUR_MODEL_TAG" --runtime-id "YOUR_FROZEN_RUNTIME_REVISION" \
  --repetitions 3 --output reports/selection-acceptance --execute
```

The runtime revision should identify weights, quantization, server version,
context configuration and hardware. It is a caller declaration, not a remote
attestation. Keep these conditions fixed across both versions. The order
alternates baseline/candidate across cases and repetitions; cold starts and
other concurrent workloads can still affect latency. This first runner uses
the client's existing `Bearer local` convention, without a new authentication
or provider layer. It never downloads or activates a model, scans a subnet,
changes the registry or falls back to a cloud service.
Inspect the configured base URL before execution; a local label does not prove
endpoint ownership or identify the model weights actually served.

At most 72 calls are planned (12 cases × 2 versions × 3 repetitions). Each
finder gets its own temporary candidate library in a fresh process. Only task
text and candidate instructions reach the endpoint; expected answers and
rationales remain in the scorer. Stored results contain relative fixture
paths, status and measured counters, with no raw response or exception text.
The private manifest contains task text, local checkout paths and endpoint
metadata. Keep the whole output directory private; `reports/` is Git-ignored.

## Read the evidence and resume

`comparison.json` reports exact selection, extra selections, retrieval coverage,
round-trip latency, backend-reported prompt/completion tokens, source/corpus
bindings and evidence gaps. Missing usage stays `null`. A mismatched response
model or truncated answer cannot pass exact selection. Endpoint usage is not
independently metered; energy and monetary cost remain `null`. This does not
measure TTFT, GPU utilization, downstream task success or instruction comprehension.

The checkpoint records an operation before dispatch. Add `--resume` to the same
execution command to recheck completed observations and run only unstarted
work. The runner binds the corpus, runtime declaration, model, endpoint,
interpreter and tracked Python/skill declaration sources. `sources_match_commit`
distinguishes a working-tree snapshot from the named Git revision. Changed inputs or
sources require a new comparison after reconciling the existing run. The
comparison also verifies observation bytes against the checkpoint before
consuming them. A modified observation becomes a gap, not a new success.

An interrupted, timed-out or uncertain call is never automatically replayed.
Inspect the checkpoint and the server/process state first: a client timeout
does not prove that remote inference stopped. The Conductor's local lock and
recovery limits apply. Do not reset its states or delete an active lock to
manufacture a retry. No checkpoint result is written into learning memory or
promoted into a new routing rule.

## Decision boundary

`measurement_complete` means every planned observation has comparable model
identity and token/latency evidence; it does not mean every selection passed.
The separate `acceptance` result applies the criteria below. The public starter
remains `dataset_class: fixture` and cannot qualify a runtime. Before judging
model or skill quality, independently review a separate
corpus of actual target situations, freeze its labels and rationale before
running, and identify its review references with `reviewed_holdout`. That label
records a declaration; the runner does not authenticate those references.

Compare both versions on the same cases. Reject any new selection of an excluded
operation or missing-prerequisite case, examine every lost correct selection,
then compare latency and reported tokens. Count repeated trials as repeated
measurements, not independent tasks. Retain the baseline when evidence is
incomplete or contradictory. Neither fixture success nor a green CI changes
the active version automatically.

## Automated acceptance assessment

The existing runner now applies `exact-selection-and-abstention/v1` after
collecting its observations. This conservative policy requires exact reviewed
selection on every candidate observation, including explicit abstention on
negative cases. It names all candidate failures, new excluded selections, lost
correct reviewed selections (including abstentions), and lost required paths.
The latter also catches the two-destination regression hidden by the baseline's
lexical fallback. One failed repetition is not averaged away.

Scores are recomputed from returned paths, review availability and model flags
against the bound corpus. Stored totals and `exact_selection` labels are not
trusted as an oracle. Duplicate or mispaired observations, inconsistent review
states and paths outside the retrieved shortlist are invalid. Missing rows,
unmatched models, truncation and absent token/latency measurements remain gaps.

| Condition | Decision | CLI exit |
| --- | --- | ---: |
| Invalid input or mismatched report/corpus | Block input | 2 |
| Incomplete comparable observations | Reconcile the existing run | 3 |
| Complete measurements with candidate selection failures | Do not promote | 4 |
| No failures, but positive or negative cases absent | Collect representative cases | 3 |
| All fixture cases pass | Collect independently reviewed held-out evidence | 0 |
| All reviewed held-out cases pass | Review results, costs and applicability | 0 |

Exit zero does not authorize execution, establish a cost benefit or select a
winner. An exit of four means the measured candidate fails the criteria; it
does not request another inference attempt. The comparison and checkpoint
remain available, and resuming a completed run retains the quality refusal
without new calls. The policy never promotes a runtime or executes an operation.

An existing comparison can also be assessed offline. Supply its expected file
SHA-256 from a separately retained record. For the first CPU pass:

```bash
python scripts/benchmark_skill_selection.py \
  --assess docs/validation/skill-selection-cpu-v1.json \
  --report-sha256 7af98eadbd338dafbbb679e3b886082464b7a0b98535bf1de7de42aa7a584089
```

This prints a separate assessment and exits **4**. It reads the bounded report
and corpus, performs zero inference and leaves both inputs unchanged. Execution
and backend arguments are rejected in this mode. A matching hash identifies the
retained bytes; it does not independently attest the original runtime, private
checkpoint or corpus review. Those remain the original evidence's boundaries.

The [recorded retrospective assessment](validation/skill-selection-cpu-assessment-v1.json)
binds this assessor's source hash to the original report and corpus. It identifies
seven failing candidate observations: the six unwanted negative selections and
the incomplete two-destination selection. The original report, model scores,
measurement revisions and historical decision remain unchanged. This policy was
implemented after observing those failures; this reassessment is development
evidence, not a new model comparison or independent validation set. New inference
runs must use their own source-bound manifest and output directory.

Repository CI remains separate from model acceptance. Its README smoke wrapper
allows 90 seconds for the full `skills.checkup.cli` audit and logs its elapsed
time; other README commands retain their 30-second limit. The previous limit
was exceeded under Python 3.10 in CI runs #310 and #315 while the code suites
passed. Nonzero exits and timeouts still fail validation. This allowance does
not claim a checkup speed improvement or identify its internal slow phase.

## Retain an assessment in shared memory

The offline assessor can emit the existing Memory Hub `capture` request. This
links a selection result to its measured source commits and fingerprints,
reported source scope, corpus, runtime and inference harness, plus the assessor
revision. It retains failures and missing evidence. The source flags are copied
observations, not fresh attestations of the historical checkout or runtime.

```bash
python scripts/benchmark_skill_selection.py \
  --assess docs/validation/skill-selection-cpu-v1.json \
  --report-sha256 7af98eadbd338dafbbb679e3b886082464b7a0b98535bf1de7de42aa7a584089 \
  --memory-request botte-secrete --memory-observed-at "$ASSESSMENT_TIME"
```

Set `ASSESSMENT_TIME` to the Unix time of this offline assessment and preserve
it with the emitted JSON. It is not the original inference time. The command
reads no credentials, contacts no service, runs no inference and writes no
files. It still exits **4** for the recorded failed candidate, even though a
valid capture request was printed. Codes 3 and 4 can therefore carry useful
observations; an invalid-input result (code 2) is not a capture request. Do not
use the quality exit as a reason to replay model calls.

The [retained CPU assessment request](validation/skill-selection-cpu-memory-request-v1.json)
is a source-bound observation ready for capture, **not an ingestion receipt**.
It is an offline reassessment of the same 24 historical calls, with seven
candidate failures and no new inference. The original CPU evidence and earlier
retrospective assessment are unchanged. No configured memory endpoint was
available for this export; cross-host ingestion remains unverified.

Use the [existing Memory Hub client](shared-memory.md) with a worker identity
authorized for the destination project and the saved request:

```bash
python -m skills.memory_hub.cli call capture \
  --url "$BOTTE_MEMORY_URL" --token-file "$BOTTE_MEMORY_TOKEN_FILE" \
  --input selection-memory-request.json
```

The default visibility is `private`. Explicit `--memory-visibility project`
prepares a separate project-visible request; changing visibility does not alter
an existing private entry. Scope remains enforced by the service. Assessment
JSON is stored as a `tool` observation, quarantined and non-executable; inspect
it through `recall` with `area=observations` and query `skill-selection`.
This is not a Conductor execution episode and does not qualify a runtime or add
verified task outcomes to the trajectory ledger.

After an uncertain transport result, retry **the same saved request with the
same authenticated identity**. The existing service reuses its receipt, including
after restart. Project, visibility and assessment content bind the key; changing
only the timestamp retains that key and causes a request conflict rather than
another observation. Different assessor revisions create separate observations
but preserve the same report-derived `run_id`; they are not independent model
validations. A forgotten key remains blocked by the existing tombstone policy.

The export omits raw task text, replies, endpoints, credential paths and checkout
locations. Case IDs and logical skill paths can still be private. It limits the
UTF-8 observation to 16,000 bytes and rejects overflow instead of dropping
failure evidence. Detailed costs remain in the pinned comparison. Historical
process/checkpoint state is explicitly `not_rechecked`: inspect the original
evidence and current target prerequisites before considering any further action.

Six focused regressions exercise the real existing in-process memory service:
capture/recall, receipt reuse after restart, private/project visibility,
quarantine, changed-timestamp conflicts, input binding, redaction, size limits
and CLI boundaries. They use temporary stores and synthetic identities; they
establish no homelab transport or real-agent retrieval-quality gain.

## Review a recalled assessment before reuse

Save the existing client's `recall` response for the expected project, with
`area=observations`, query `skill-selection` and `max_bytes=65536`. Then review
that snapshot against the pinned comparison and a caller-selected checkout:

```bash
python scripts/benchmark_skill_selection.py \
  --assess docs/validation/skill-selection-cpu-v1.json \
  --report-sha256 7af98eadbd338dafbbb679e3b886082464b7a0b98535bf1de7de42aa7a584089 \
  --memory-recall recall.json --memory-project botte-secrete \
  --memory-target /absolute/path/to/current/checkout
```

This mode reads only caller-selected inputs and runs Git to sample that checkout's
tracked source footprint. It opens no remembered path or reference, reads no
credential, calls no service or model, writes nothing and executes no skill.
It cannot be combined with inference or capture-export inputs.

`memory_review` checks the retained assessment against freshly recomputed
selection results and bound context. The original assessor hash is retained,
with `assessor_changed` reported separately. It verifies the generated observation
key, text digest, source and evidence references, and untrusted/non-executable
labels. Altered scores remain invalid even with a new internally consistent key
and digest. Expired entries, duplicate keys, wrong project/area and malformed or
oversized input cannot silently become reusable evidence. Only matching entries
count, and several assessments of this comparison still count as one report.

`source_check` compares the measured candidate with the chosen checkout's commit,
tracked source hash, scope, file count and committed-source flags. A changed or
uncommitted footprint returns `source_changed`. The footprint includes tracked
Python and skill declarations, not just the finder; a difference alone does not
diagnose a finder regression. This is a sampled read, not an execution lock.

CLI exit **3** requests review when the recall is missing/incomplete or sources
differ, while retaining the original quality refusal in `acceptance`. If recall
and recorded sources match, the ordinary quality exit applies (4 for this CPU
comparison). Malformed input returns 2. A matching source footprint still leaves
runtime, current memory-service state and task prerequisites unchecked. No
execution, reuse, promotion or retry is authorized by a zero exit.

All recall remains a bounded sample. Omitted entries, a truncated pool or a full
20-entry response are marked incomplete; even an untruncated response does not
establish exhaustive history. A saved response cannot prove the service still
retains an entry or that an issuer is authentic. Hashes bind supplied bytes;
they do not independently attest historical execution or oracle quality.

The [recorded recall review](validation/skill-selection-memory-review-v1.json)
uses the unchanged CPU evidence and the previously published `f01d212` checkout.
It preserves the seven failures and reports source drift from measured candidate
`8f2bd6e`. A temporary loopback HTTP service and two synthetic identities exercise
private exclusion, project-visible recall and offline review. This is one-host
transport evidence with no new model calls or production-memory ingestion.
