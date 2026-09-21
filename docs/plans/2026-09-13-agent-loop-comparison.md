# Measuring complete agent loops

## Why the compression result is insufficient

The [compression comparison](2026-09-13-compression-integrity.md) measured one
component on seven synthetic fixtures. It measured neither task execution nor
avoided model turns. Botte also has lazy tool discovery, deterministic repository
exploration, local pipelines, context selection, caches and local routing.
Their combined effect depends on the task and must be measured as a complete run.

## Preparation completed

The existing `loop_optimizer.baseline.compare` incorrectly accepted two failed
runs as comparable. A four-iteration, 1,000-token failure against a one-iteration,
100-token failure reported 90% savings. Missing token counts could also become
zero, and extra candidate iterations were hidden by a clamp.

The comparison now requires explicit boolean success from both reports and
complete nonnegative integer token/iteration counts. Invalid or unsuccessful
pairs receive no savings credit; signed iteration differences expose regressions.
Four native regression tests cover these cases. This validates accounting rules
over supplied reports, not the truth of their success/usage claims or task equality.

The MCP `loop_stats` response is also missing on the base tree, but its existing
fix belongs to [PR #57](https://github.com/zedarvates/botte-secrete/pull/57).
Reuse that work when preparing an integrated candidate; this slice does not
duplicate the server change or merge either PR. A global ledger summary must not
be treated as one task's success just because its last record reports success.

## Another measured component: tool discovery

`python scripts/measure_tool_catalog.py` measures the full and lazy catalogs.
Its default is UTF-8 bytes with token counts left unmeasured. Add `--tokens`
with an already installed `tiktoken` and cached `o200k_base`. Missing dependencies
or caches fail; the command installs nothing and blocks Python socket connects.

The [retained measurement](../validation/compression-integrity/tool-catalog.json)
records serializer, tokenizer, source digests and serialized-content digests:

| Catalog | Listed tools | Serialized tokens |
|---|---:|---:|
| Full | 61 | 6,244 |
| Lazy, including `find_tool` | 5 | 605 |

This is a 90.31% reduction of the initial serialized catalog. It excludes lookup
requests/responses, subsequent loaded schemas, task messages, tool results and
provider/cache accounting. There were zero LLM calls. Do not add this percentage
to the compressor's 21.46%, multiply it by an assumed turn count, or report it as
a task saving. Small tasks may gain nothing once discovery overhead is included.

## Next executable comparison

Start with three task families on the same frozen checkout: locate a named
symbol and its tests; diagnose a cross-file failure; make a bounded correction
and pass the same acceptance tests. Include an unchanged repeat and a changed-file
repeat to check cache reuse and invalidation. Keep failed tasks and retries.

Use the same model, tokenizer, task instructions, permissions, starting files,
output budget and acceptance checks. The ordinary agent baseline retains its
normal batching abilities; do not force unnecessary sequential calls. Compare:

1. Ordinary agent/tool workflow.
2. The same workflow with Botte discovery, relevant-context collection and
   grouped deterministic operations.
3. The second arm with the corrected compressor. Add cache/local-routing arms
   only when their environment and accounting are actually available.

Record each actual model request/response and tool execution, with stable run,
request and parent identifiers. Record task/model/config/source digests and keep
private prompts/code out of public evidence. Grouped tools count as multiple
tool operations within one model turn; discovery, verification, retries and the
final answer all count toward the run. Capture:

- model turns and tool operations, including local model calls;
- input/output tokens per request, with usage source and unknown values explicit;
- cached input tokens as a subset of input, not an extra quantity to add;
- complete wall time, local execution time and retries;
- identical acceptance results, failure details and changed-file validity.

Compute paired task totals from observed requests. Report successes and failures
together, and compare savings only for equivalent successful outcomes. Run-level
wall time must not be reconstructed by summing overlapping tool durations.

There is no complete-agent inference result in this slice. The next requirement
is a reachable model and a trace-enabled agent harness. Existing default-zero
ledger fields and the metrics module's assumed 30 turns are insufficient evidence.
This preparation starts no collector, changes no routing and activates no model.

## Harness registry IDs and optional Protobuf transport

The next design can give MCP tools, CLI operations, agent entry points, skills
and workflows a common capability reference. Reuse `capabilities.registry` and
the existing gateways, including the source-identity/effects work in PR #108.
Serialize descriptors, invocation arguments and results; executable code and
skill instructions keep their original implementations and semantics.

Use a stable, origin-scoped capability identity and a pinned descriptor revision.
A short session alias can point to that identity. The alias must never mean an
array position: list reordering, a new server or a changed schema must not silently
redirect an old call. Example negotiated entries (illustrative, not implemented):

| Alias | Operation | Adapter |
|---|---|---|
| `C17` | Find an exact symbol and relevant tests | Repository search |
| `C23` | Run a selected test target | CLI argument vector |
| `W4` | Execute a declared diagnostic plan | Workflow |

The model sees selected names, concise suitability information and required
arguments, with complete instructions/effects available before use. It can then
refer to the negotiated alias, for example `{"cap":"C17","args":{"symbol":"restore"}}`.
An opaque ID alone is insufficient for choosing a capability. A shared execute
operation must still validate each referenced capability's argument schema and
current authorization. A skill reference does not make its instructions executable.

The harness resolves aliases and handles dependencies, batching and retained
result references. It must preserve failures, partial effects and required facts;
unknown/stale aliases or missing result handles cause an explicit failure, not a
silent alternative operation. Request/run IDs track duplicates and resume state;
Protobuf by itself supplies neither exactly-once execution nor authorization.

Keep the existing MCP boundary as JSON-RPC. Its standard transports require the
[JSON-RPC message format](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
Protobuf can be an optional internal harness-to-worker codec, translated by
adapters. It reduces repeated field-name overhead on that binary link; it does
not itself reduce model turns or establish LLM token savings. Model-visible
messages remain compact structured text, never a dump of binary/base64 payloads.

When testing that codec, use generated implementations with versioned schemas,
explicit presence for optional measurements and an unspecified default status.
[Field numbers must not be reused](https://protobuf.dev/programming-guides/proto3/).
Keep semantic/source identity hashes separate from raw wire-byte digests:
[Protobuf serialization is not canonical](https://protobuf.dev/programming-guides/serialization-not-canonical/).

First compare the registry/alias design using existing JSON adapters. Then test
an optional Protobuf codec with the same operations and complete results. Measure
wire bytes and encoding time separately from actual model tokens, model turns
and task correctness. Include discovery overhead, required description loads,
result retrieval, unknown IDs, registry revisions, Unicode, missing fields and
duplicate requests. No Protobuf codec or alias dispatcher is implemented here.
