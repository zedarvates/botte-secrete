# Needle 2: bounded calibration and first generalist comparison

Decision: **stop this threshold-only study; keep the pilot consultative**.
On a new 20-case calibration split, changing the threshold cannot recover the
missing exact calls. A small CPU generalist is also inadequate on this sample.
This is a completed exploratory comparison, not a homelab acceptance result.

## What was actually measured

The [protocol](validation/needle2-study-protocol-v1.json), implementation, model
catalog and two authored French splits were frozen in local commit
`17fff9a` before the first inference of this study. The original 48-case corpus
was not reused for selection. The new calibration split has 10 positive cases
(two for each tool) and 10 negative cases. The separate validation split has
the same counts and has **not been run**.

| Configuration | Exact positives / 10 | Wrong proposals on positives | Unwanted proposals / 10 negatives | Exact / all proposals |
|---|---:|---:|---:|---:|
| Needle 2, threshold 0 | 4 | 3 | 4 | 4/11 |
| Needle 2, threshold 0.65, retrospective filter | 2 | 0 | 0 | 2/2 |
| Needle 2, threshold 0.9, retrospective filter | 0 | 0 | 0 | No proposals |
| Qwen2.5-0.5B Instruct, Q8_0 | 4 | 6 | 6 | 4/16 |

There were **20 real native Needle requests and 20 real local-generalist requests**,
with no runtime errors, no corrective retry and no tool execution. Threshold
rows above zero are filters over the same archived native proposals, not new
inferences. Needle's exact proposal precision is 36.4%; Qwen's is 25%.

The recorded P95 parent/worker round trip for Needle is 375.028 ms, versus
1388.217 ms for Qwen's HTTP round trip in this Linux CPU environment. Needle's
first request includes worker initialization; the Qwen server loaded its weights
before requests. Qwen ran with four CPU threads, one slot, 4096-token context,
GPU layers zero, prompt caching disabled and no Web UI. These are observations
of different execution paths, not a production speedup or a fallback-adjusted
latency claim. Native peak memory, power and homelab latency were not measured.

Full records: [Needle](validation/needle2-study-calibration-native-v1.json),
[generalist](validation/needle2-study-calibration-generalist-v1.json),
[paired summary](validation/needle2-study-comparison-v1.json),
[threshold selection](validation/needle2-study-selection-v1.json), and
[execution evidence](validation/needle2-study-validation-v1.json).

## Selection and stopping rule

The fixed grid is `0, 0.1, 0.2, 0.4, 0.6, 0.65, 0.8, 0.9`. Choose the most exact
positives among settings with **zero incorrect proposals on either class**;
break ties with the higher threshold. Continue to validation only if that choice
retains at least 5/10 positive calls spanning at least three of the five tools.
This modest breadth requirement is an experimental usefulness rule chosen before
measurement, not a safety guarantee or an activation gate.

The best diagnostic choice, 0.65, retained just one history call and one scribe
call. The selector therefore recorded `stop_insufficient_safe_coverage` with
`selected_threshold: null`. Validation is blocked by the runner. A valid
proposal's score is not a correctness probability or an execution permission.

Even at threshold zero, only four positives are exact. Raising a filter cannot
increase that maximum for the frozen outputs. Further threshold searching on
this corpus is not justified. Changing tool descriptions, output handling or the
model would be a new experiment with new source fingerprints and an appropriate
new evaluation split. Do not normalize optional empty queries or letter case
after seeing the scores to improve the headline metric.

## Reproduce without changing default routing

Use Python 3.10+ for the study runner. The native worker in this run used Linux
x86-64 / Python 3.12.14 and `cactus-needle==2.0.13`; see the
[existing setup guide](needle2-memory-pilot.md#reproduce-on-linux-x86-64) for its
pinned library. Only run the following against an explicitly provided local
library and an output directory you have created. Output files and their
`.jsonl` journals must not already exist.

```bash
python -m skills.tool_router.needle2_study run --backend needle --split calibration --library /path/to/libneedle.so --engine-python /path/to/needle-python --output /path/to/results/needle.json
python -m skills.tool_router.needle2_study select --calibration /path/to/results/needle.json --output /path/to/results/selection.json
```

For the generalist, create a **private, untracked** JSON configuration. Use the
exact identifier returned by your server. The weight fingerprint, quantization
and runtime version must describe the model actually installed; these values
are operator-supplied provenance, not remote attestation. No endpoint discovery,
download or cloud fallback occurs in the runner.

```json
{
  "base_url": "http://127.0.0.1:1234",
  "model": "EXACT_SERVER_MODEL_ID",
  "weights_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_CHARACTERS",
  "quantization": "INSTALLED_QUANTIZATION",
  "runtime_version": "INSTALLED_RUNTIME_VERSION",
  "timeout_seconds": 30
}
```

An optional `api_key_env` names an environment variable containing the key.
The key and endpoint are not copied into the report. URLs must be loopback or
literal private LAN addresses; credentials in URLs, proxies and redirects are
disabled. The endpoint is `/v1/chat/completions`; no memory service is contacted.

```bash
python -m skills.tool_router.needle2_study run --backend generalist --split calibration --generalist-config /path/to/private-config.json --output /path/to/results/generalist.json
python -m skills.tool_router.needle2_study compare --needle /path/to/results/needle.json --generalist /path/to/results/generalist.json --output /path/to/results/comparison.json
```

Omitting `--generalist` from `compare` produces `generalist: "not_measured"` and
`paired_comparison_measured: false`. Missing infrastructure, partial runs and
HTTP failures must not be interpreted as model abstentions or quality results.
The runner stops on the first runtime failure, writes the partial report and
returns exit code 3. Invalid configuration/provenance or existing output returns
2. Exit code 0 means the command completed, even when selection says to stop.
Inspect the per-case journal after an interruption before scheduling any new
run; there is no implicit retry or resume that can duplicate inference silently.

The reserved validation phase requires both `--selection` and `--calibration`.
The selection must be exactly reproducible from a complete calibration report
under this protocol and must say `candidate_for_validation`. The recorded study
did not meet that condition, so no validation command was executed.

## Fairness and limits

Both models receive the same query and the same five tool names, descriptions
and argument schemas, retaining schema order. Each request has fresh dialogue
context. Needle uses its native tool-call path. Qwen receives the catalog in a
fixed JSON-selection prompt, with `temperature: 0`, a 256-token output limit and
`response_format: json_object`. No examples, repair retries or argument extraction
heuristics are added. Generalist outputs pass the same memory schema validation;
its stored score of 1 is a bookkeeping value, not model confidence, and is never
used for Needle threshold calibration. This compares these concrete adapters,
not every possible prompt or tool-calling mode of either model.

The small generalist is a low-cost reference, not a claim about the best model
for a 12 GB GPU. Its weights came from the official
[Qwen repository at the pinned revision](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67),
with `qwen2.5-0.5b-instruct-q8_0.gguf` SHA-256
`ca59ca7f13d0e15a8cfa77bd17e65d24f6844b554a7b6c12e07a5f89ff76844e`.
The official [llama.cpp b10809 CPU build](https://github.com/ggml-org/llama.cpp/releases/tag/b10809)
archive had SHA-256
`5e34434ddc6d03cd1584f403201aff0d4bd1a5793a72ff7e286532dfd1e4b941`.
Downloaded bytes were checked before execution. Weights and binaries are not
redistributed in this repository. The temporary local server was stopped after
the 20 requests.

These are newly authored synthetic workflow proxies. Split IDs and exact queries
are disjoint, but the author, intent families and tool catalog are shared; this
is not an independent held-out evaluation of actual user tasks. Twenty cases
cannot establish rare-error safety. Neither model may become an automatic
router on this evidence; all outputs keep `executable: false`, and all study
records keep `executed: false`, `activation_allowed: false`, zero tool calls and
zero memory writes. Records are ineligible for the successful-action ledger.

The new tests cover provenance, strict output validation, a local fixture HTTP
exchange, redirects, partial-run handling and validation gating. CI uses fixture
engines; it does not install or download either model. See the execution evidence
for the recorded native runs and software checks. No homelab connection,
Windows acceptance, deployment, merge or default threshold change occurred.
