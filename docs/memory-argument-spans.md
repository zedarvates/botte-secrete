# Memory arguments copied from source spans

Status: **implemented software candidate, model quality unmeasured**. This
separate candidate follows the [frozen error diagnostic](needle2-error-diagnostics.md).
It does not change the Needle/Qwen adapters, their catalog, their historical
scores, the threshold stop decision or the reserved validation split.

`bind_argument_spans(query, proposal)` copies each supplied query span into a
memory argument, then applies the existing memory schema. A producer identifies
the tool and the positions; the host performs the copy. The binder runs no model,
selects no passage itself and never executes the resulting proposal.

## Input contract

The proposal has exactly four fields:

| Field | Meaning |
|---|---|
| `schema_version` | `botte.memory-argument-spans/v1` |
| `query_sha256` | Host-provided SHA-256 of the original query encoded as UTF-8 |
| `tool_name` | One of the five existing memory-pilot tools, or `null` |
| `argument_spans` | Argument names mapped to objects containing integer `start` and `end` |

Positions count **Unicode code points**, beginning at zero, with an exclusive
end. They follow Python string slicing. Producers using UTF-8 bytes or UTF-16
code units must convert their positions; combining marks and emoji variation
selectors each occupy a code point. The original query is never normalized.

For the complete query `Consulte l'historique de lot_MOTEUR-8.`, the key occupies
positions 25 through 36, so its span is `{"start": 25, "end": 37}`. The host
copies `lot_MOTEUR-8` exactly. The [complete input example](examples/memory-argument-spans-v1.json)
includes the query digest, and its [recorded result](validation/memory-argument-spans-example-v1.json)
includes fingerprints of the input bytes, binder code and current memory catalog.
This example was authored for the software contract; no model produced it.

The producer echoes a digest supplied by the host; it need not calculate that
digest itself. A mismatch rejects a stale proposal. This correlation marker
does not authenticate a producer or establish the user's intent or permissions.

## Binding rules

- One nonempty, contiguous span supplies each argument. Text is copied without
  trimming, case conversion, Unicode normalization, concatenation or repair.
- Omit an optional argument by leaving it out of `argument_spans`. An empty map
  stays an empty argument object. Zero-length spans are rejected, so this
  candidate representation has no explicit empty-string value.
- Booleans, floats, strings, reversed spans and out-of-range positions are
  rejected as coordinates. Missing required arguments and invalid copied
  identifiers/text are rejected by the existing memory schema.
- Only declared memory-pilot arguments are accepted. Project, identity, rights
  and execution flags cannot be supplied through spans or extra envelope fields.
- `tool_name: null` with an empty map is explicit abstention. Every invalid
  proposal also abstains, preserving a reason and no partial arguments.
- Results always have `executable: false` and confidence zero, marked unmeasured
  in CLI output. The host can separately build a reviewable call using the
  existing `memory_call(route, project_id)` function and its own project context.

## Run the software example

From a complete checkout with Python 3.10+, choose an output path that does not
exist. Its parent directory must already exist.

```bash
python -m skills.tool_router.argument_spans --input docs/examples/memory-argument-spans-v1.json --output argument-spans-result.json
```

The input file contains only `query` and `proposal`, is bounded to 8192 bytes,
and rejects duplicate JSON keys. The query is bounded to 512 UTF-8 bytes. The
command prints a compact status and writes the reviewable result; existing
files are never overwritten. Exit code 0 means a structurally valid proposal
or explicit abstention. Code 2 means rejection or an input/output error. A
rejected proposal produces an abstention report; malformed input produces no
report. These codes do not establish semantic correctness.

## Proven and still unmeasured

Tests use newly authored software examples to check exact copying, Unicode,
optional-argument omission, invalid input rejection, query correlation and
compatibility with all five existing memory-call schemas. They also deliberately
show that a valid span inside a negated request can still bind successfully.
Literal copying is therefore insufficient to choose the correct passage, detect
negation or authorize an operation.

The candidate has no automatic registration, model connection, memory-service
call or Atlas persistence. These tests and the example are not an independent
held-out corpus or a new Needle/Qwen comparison. Offset-generation accuracy,
false proposals, useful coverage, prompt overhead and end-to-end latency remain
unmeasured. Before any model comparison, define and freeze a separate protocol,
candidate prompt/catalog and fresh labeled evaluation data including negatives;
keep the existing reserved split untouched. No gain or activation follows from
the software tests alone.
