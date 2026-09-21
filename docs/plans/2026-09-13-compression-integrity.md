# Compression integrity and bounded Headroom comparison

## Decision

Keep Botte's existing stdlib compressor and optional Caveman prompts. Repair the
observed integrity defects before adding an upstream runtime dependency.
Headroom remains an experimental comparison arm; Caveman's BSL engine is not
bundled. This updates the compression work in the
[Fable6 plan](2026-07-04_fable6-plan.md).

## Corrected behavior

- Reversible keys hash all UTF-8 bytes with SHA-256. Two originals sharing their
  first 256 bytes no longer overwrite one another. Identical originals deduplicate.
- JSON compaction removes whitespace outside strings only. It retains late
  errors, deep fields, long strings, duplicate keys and exact number lexemes.
- Code remains byte-identical; `#` inside a string cannot become a comment cut.
- Logs preserve distinct values, full lines and chronology. Exact consecutive
  repeats can be summarized; tool output only loses ANSI formatting.
- Both compression MCP surfaces return their complete result. Empty originals
  remain distinguishable from missing recovery keys.
- Public compressor sizes are UTF-8 bytes. Caveman file analysis returns the
  full unchanged text and zero transformation savings; style savings remain
  unmeasured. Its token counts are explicitly character-based estimates.
- The full benchmark's schema 2 totals sum only compressor UTF-8 bytes, through
  `total_input_bytes` and `total_output_bytes`. Mixed-unit character totals and
  the arbitrary monthly projection are removed. The README chart is regenerated.

The CLI and MCP still use the existing APIs. Old 12-character reversible keys
are not migrated: this store is process-local, with no durable restoration.
This change adds no store, model activation, collector or routing decision.

## Regression evidence

The new tests were exercised against the old implementation before the fixes:
cache aliasing, JSON omission, source corruption, log/tool truncation, both MCP
cuts, UTF-8 size mismatch and Caveman's fixed estimate all failed.

The two compressor/Caveman suites then passed 41 tests. Four additional benchmark
tests retain zero-gain cases and reject missing failures, altered authority and
altered tool-call identity. All three suites are registered in the canonical
runner, so the Python 3.10/3.11/3.12 CI executes them without pytest.

```bash
python -m skills.universal_compressor.test_universal_compressor
python -m skills.caveman.test_caveman
python -m skills.universal_compressor.test_benchmark
python scripts/run_tests.py -q
```

The preservation assertions replace earlier tests that rewarded dropped array
items or removed imports. This intentionally changes the tested contract toward
retaining source information, rather than reducing a validation threshold.

## First component comparison

The [raw report](../validation/compression-integrity/headroom-0.37.0.json) contains
all seven public synthetic fixtures, all output messages, protected-fact checks,
input/output digests, source and harness digests, timings and tokenizer counts.
The [environment record](../validation/compression-integrity/environment.json)
pins the installed wheels by version and SHA-256. This tests the PyPI
`headroom-ai==0.37.0` wheel, not an asserted equivalent of GitHub `main`.

| Arm | Serialized-message tokens before | After | Direct protected-fact checks |
|---|---:|---:|---:|
| Original | 8,659 | 8,659 | 7/7 |
| Botte corrected | 8,659 | 6,801 | 7/7 |
| Headroom 0.37.0, direct library output | 8,659 | 5,117 | 6/7 |

Botte reduced these tokenizer counts by 21.46%. Headroom's 40.91% direct
reduction fails one protected-fact check and is not an accepted saving at the
required visible evidence level. In `json_long_value`, `NOT_AUTHORIZED` becomes
a CCR marker while `PENDING_CI` remains visible.

A separate deterministic inline-recovery probe on that failing row retrieves the
marker, restores equal JSON values and passes its protected-fact check. Its
output grows from 109 to 636 serialized-message tokens. This does not change the
direct arm's failing result or its nonzero process exit. The probe already knows
which row failed: it does not prove that an LLM will request retrieval when needed.

Boundaries:

- These are seven synthetic component fixtures, not coding tasks, homelab
  inference, model-answer quality, invoices, or independent private holdout.
- The same cached `tiktoken` `o200k_base` tokenizer counts serialized messages for
  all arms. This is not a provider's message accounting or a Qwen tokenizer.
- Botte receives explicit content types. Headroom detects them through its public
  library API. `protect_recent=0` permits the fixture tool output to be processed;
  the first three messages are frozen, system compression is disabled and
  Kompress is disabled. This is not the default agent-wrapper configuration.
- Native content detection reported a fallback to Python because optional ONNX
  Runtime 1.24+ was absent. This remains visible in the environment record.
- Zero-gain rows stay in the result. Timing is one call per case, including cold
  initialization on the first call; it does not support a latency ranking.
- Offline flags and a Python socket-connect guard apply during the CLI run.
  The guard is not OS isolation of native extensions. No LLM/provider is invoked.
- Unicode JSON escapes in the fixture can become literal Unicode during recovery;
  equal values can therefore have very different tokenizer costs.

## Reproduction

The stdlib baseline requires no added dependency and leaves token counts unmeasured:

```bash
python -m skills.universal_compressor.benchmark
```

For the upstream arm, use a separate environment with the wheel versions and
hashes recorded above. Prepare `o200k_base` and `cl100k_base` tokenizer caches
before the offline run. The harness never installs dependencies, starts a proxy,
changes agent configuration or downloads model weights.

```bash
python -m skills.universal_compressor.benchmark --headroom --tokens
```

This command currently exits 1 because the direct Headroom arm fails one gate.
Inspect the JSON report; do not remove that case or reinterpret it as a passing
LLM comparison. Runtime/import failures also remain failures, not fallback wins.

## Next bounded slice

1. Specify an explicit retrieval-or-original fallback for omitted protected data,
   including expired/missing handles and process restart. Keep original permissions
   and source identity. Test it as an adapter before adding it to a live agent.
2. Compare uncompressed input, corrected Botte and that adapter after the same
   SCOUT/context selection, with the same local model and tokenizer. Include prompt
   overhead, retrieval calls, retries, cache effects, wall time and answer quality.
3. Evaluate concise French output separately using paired actual model responses;
   preserve conditions, uncertainty and evidence. A style setting alone is no gain.

Headroom's [Apache-2.0 license](https://github.com/headroomlabs-ai/headroom/blob/aa4739e54ad46d48dd829f730af359c4824c04c4/LICENSE)
supports reuse with its notices. Caveman's
[license map](https://github.com/JuliusBrussee/caveman/blob/15581d14007fd01fb3f132016741962f34936ca2/LICENSING.md)
separates MIT skills from its BSL engine/proxy/MCP. No Caveman engine code is
copied here. Keep telemetry disabled in any future upstream experiment.
