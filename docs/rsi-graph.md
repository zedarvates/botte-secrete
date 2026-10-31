# Read-only RSI graph

The observer groups recorded Botte events by explicit producer, component and
event kind. It counts adjacent observations without changing the project,
routing policy, tools or models.

```bash
botte rsi observe /path/to/project --json
botte rules audit /path/to/project --json
```

The first command reads only the selected project's `.botte/events.jsonl`.
The second audits that project's committed `.botte/rules.json`; it does not
execute probes. A missing rules manifest returns exit 2. The repository's
strict CI gate additionally requires all three registered RSI rules and rejects
warnings as well as errors.

## Reading the graph

- `observed_next` means adjacency in file order. It is neither causality nor a
  dependency, and events from overlapping runs can be interleaved.
- Producer IDs encode the full identity tuple as JSON, so delimiters and absent
  components cannot merge distinct producers. Legacy events retain unknown
  producer provenance. Identity fields must be non-empty UTF-8 strings when
  present; `kind` is required.
- Malformed records, duplicate JSON fields and nonfinite constants are rejected.
  A rejected record breaks the adjacency chain rather than linking across a gap.
- Cost, tokens, compute and energy remain `null`. No measured savings or model
  quality is inferred from event counts.

Always inspect `source_status` and `rejected_records`. Exit 0 can accompany a
`missing` or `partial` source; it means observation completed, not that history
is complete. `unavailable`, `invalid` UTF-8 and `too_large` sources return exit 2.
An empty readable file is distinguished from a missing source.

Input is limited to 5 MiB plus one sentinel byte. Detected symlinked log paths
and non-regular files are refused, with nonblocking open where supported to
avoid FIFO waits. These guards are not an OS sandbox, a guarantee against
concurrent directory substitution, a wall-clock deadline for filesystem I/O,
or an atomic snapshot of a log being modified.

## Contracts and evidence

The [RSI schema](schemas/rsi-graph-v1.schema.json) describes the report. The
[experimental capability schema](schemas/capability-graph-v0.schema.json)
describes capability metadata only. It does not connect the graphs, resolve
prerequisites or grant execution authority.

The [registered rule contract](../.botte/rsi-rules.md) binds rule semantics and
exact source/probe anchors. Its fingerprint and `last_verified` receipt do not
hash complete implementation bodies or prove a probe was executed. Behavioral
evidence comes from the tests run on the exact candidate.
