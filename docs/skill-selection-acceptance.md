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
