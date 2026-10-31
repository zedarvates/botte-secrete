# Replay the Parcimonia workflow demonstration

Run this from a Botte Secrète candidate checkout with Python 3.10 or newer:

```sh
python examples/parcimonia_workflow_demo.py
```

It prints five authored examples: French GitHub research, English software
testing, French game playtesting, an ambiguous task and a negated task. It also
prepares a repository-scoped search plan and a PR plan. It uses the existing
`assess_task` and `plan_github_research` helpers without a network or model call.
The small supplied tool inventory is illustrative metadata; the example does
not verify, connect or execute these tools.

To retain the full output, select a new absolute directory outside the checkout:

```sh
python examples/parcimonia_workflow_demo.py --out /tmp/parcimonia-demo-run-1
python -m json.tool /tmp/parcimonia-demo-run-1/parcimonia-workflow.json
```

On Windows, use an external directory such as
`C:\Temp\parcimonia-demo-run-1`. A relative path, a destination inside the
checkout, or an existing report is rejected. The command creates at most one
64 KiB JSON report and never overwrites it. Choose another directory to replay.
The first command without `--out` writes no report.

To add a real observation collected by the host's GitHub reader, use:

```sh
python examples/parcimonia_workflow_demo.py --github-report /absolute/path/pr-observation.json
```

The optional file uses the [GitHub evidence envelope](../parcimonia-workflow.md),
is limited to 128 KiB, and is kept separate from authored examples. The command
summarizes only that supplied observation, preserving its input hash and the
helper's byte measurements. It does not fetch, authenticate or verify GitHub.
Prefer file headers to full patches when reviewing metadata. Input projection,
MCP framing, host reasoning and later reads are outside the JSON size measure.

The JSON preserves the helper results, source-file hashes, runtime/Python
versions, fixture outcomes, and the following measurements:

| Field | Meaning |
| --- | --- |
| `helper_wall_ns` | One synchronous helper call, measured with `perf_counter_ns`; import, encoding, host reasoning and external work are excluded. |
| `result_utf8_bytes` | Exact size of that helper's compact JSON result in UTF-8. |
| `provider_tokens`, `cost`, `end_to_end_latency_ms`, `savings` | Unknown, retained as `null`. |

The examples' outcomes should repeat on the same source, while clock readings
and timestamps vary. Their checks are smoke checks for these authored inputs,
not held-out task accuracy. The timings are not a baseline/candidate speed
comparison, and bytes are not tokens or billed usage.

## Record the English introduction

Use the [spoken script and storyboard](parcimonia-introduction.md) with the
terminal output above. A short opening for the recording is:

> Here is a reproducible preview of Parcimonia. It prepares a first assessment,
> suggests tool candidates and plans GitHub reads. In this offline replay,
> those are proposals. The host agent performs the actual work separately.

Keep the abstention and the game's missing adapter/latency/stop prerequisites
visible. This example does not run a software test, read live GitHub data or
play a game. To record an execution, replace the illustrative inventory with
the actual session's tools, then have the host perform the selected action and
retain its command, result, target revision and independent checks. Label that
segment separately from this replay.

For a live PR segment, use the observed PR number and metadata. Confirm
`merged`/`merged_at`, exact head checks, base identity, and incomplete reads;
the example's PR 147 is a fixed demonstration target, not a claim about its
current status. The public-directory installation and performance segments
remain subject to the evidence requirements in the introduction draft.
