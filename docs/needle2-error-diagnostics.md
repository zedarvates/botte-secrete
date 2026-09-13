# Needle 2: offline calibration error diagnostics

This diagnostic explains the archived
[Needle/Qwen calibration](needle2-calibration-study.md). It adds no inference,
threshold filtering, argument repair or new model-quality measurement. The
study decision remains `stop_insufficient_safe_coverage`, with no selected
threshold and no activation.

The [reproducible JSON report](validation/needle2-error-diagnostics-v1.json)
links every observation to its calibration case ID. It separates wrong tools,
wrong arguments, missed positive calls and proposals on negative cases. Counts
are also grouped by the expected tool; argument differences distinguish missing,
unexpected and changed fields without normalizing text or optional values.

## Observed failure categories

These describe the same 20 archived calibration cases per model at threshold
zero. Positive and negative classes each contain ten cases.

| Outcome | Needle 2 | Qwen2.5-0.5B Instruct Q8_0 |
|---|---:|---:|
| Exact positive call | 4 | 4 |
| Wrong tool on a positive case | 1 | 1 |
| Right tool, wrong arguments | 2 | 5 |
| Abstention on a positive case | 3 | 0 |
| Proposal on a negative case | 4 | 6 |
| Abstention on a negative case | 6 | 4 |

An abstention describes the final adapter output. It is not necessarily a
deliberate model choice. Of the six negative Needle abstentions, three carry
`model_abstained`, one `invalid_arguments` and two `ungrounded_arguments`.
Of the four negative Qwen abstentions, one carries `model_abstained` and three
`invalid_model_output`. The report preserves these recorded reasons separately
for positives and negatives; it cannot establish the model's internal intent.

## What the cases help investigate

- `cal-wiki-2`: the label has no arguments; Needle added `query: ""`, and Qwen
  added `query: "projet"`. Both remain incorrect under the frozen exact metric.
- `cal-history-2`: Qwen changed the literal key `devis_laser_2` to
  `devise_laser_2`. Needle preserved both history keys in this small sample.
- `cal-context-1`: Needle proposed a scribe operation instead of context
  retrieval. Qwen selected the right operation but changed the search text.
- `cal-observations-1`: Needle changed the query; Qwen selected the wiki.
  Distinguishing reviewed context, quarantined observations and wiki content
  remains a useful question for a separate catalog experiment.

The next justified design question concerns operation descriptions and exact
argument preservation, while retaining negative cases and abstention. These
examples do not prove that a catalog change, deterministic extractor or narrower
router will improve quality. Any such candidate needs a separate frozen protocol
and fresh evaluation data. The existing reserved validation split stays unused;
this report neither selects a candidate nor authorizes another model run.

## Reproduce

From a complete checkout with Python 3.10+, choose an output filename that does
not exist, in an existing writable directory:

```bash
python -m skills.tool_router.needle2_diagnostics --output needle2-errors.json
```

The command writes the complete JSON and prints compact outcome counts. It uses
the standard library and existing memory schemas, with no model setup, network
request or service discovery. Exit code 0 means the diagnostic was written;
2 means invalid input or an output error. Existing files are never overwritten.

The v1 manifest is pinned by SHA-256. Its referenced artifacts are checked, the
protocol verifies its code/catalog/corpus fingerprints, and the recorded scores,
comparison and stop decision are recomputed before classification. The reserved
corpus is read by the existing protocol integrity check but is not diagnosed,
scored or sent to a model. The output includes its diagnostic-source fingerprint.
This is integrity and score reproduction, not independent attestation of the
historical model execution.

The CI checks deterministic reproduction, exact argument differences, altered
archive rejection, runtime exclusion and output collisions. No tools are
executed, no memory is written and no successful-action ledger record is
eligible. Native/HTTP latency remains incomparable as an end-to-end speedup;
homelab, Windows and independent user-task quality remain unqualified.
