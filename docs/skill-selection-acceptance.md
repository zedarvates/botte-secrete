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
The public starter remains `dataset_class: fixture` and always asks for held-out
evidence. Before judging model or skill quality, independently review a separate
corpus of actual target situations, freeze its labels and rationale before
running, and identify its review references with `reviewed_holdout`. That label
records a declaration; the runner does not authenticate those references.

Compare both versions on the same cases. Reject any new selection of an excluded
operation or missing-prerequisite case, examine every lost correct selection,
then compare latency and reported tokens. Count repeated trials as repeated
measurements, not independent tasks. Retain the baseline when evidence is
incomplete or contradictory. Neither fixture success nor a green CI changes
the active version automatically.
