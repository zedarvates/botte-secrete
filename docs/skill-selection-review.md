# Local skill selection review

The `skill_finder` lexical search produces a shortlist. Its optional `--local`
mode sends the retained candidates' complete `SKILL.md` bodies to the configured
local model. This is a review of candidate relevance, not an executor or a
verification of the requested operation's live prerequisites.

## What changed

The earlier implementation gave the model only names and shortened descriptions,
converted its numbered answer back to names, and then sorted the entire original
shortlist. Equal names could lose the requested ordering, rejected candidates
remained present, and no valid empty selection was possible.

The updated implementation maps numbered answers to paths, returns only retained
candidates in their requested order, and treats `0` as explicit abstention.
`local_rerank()` still returns names by default for existing callers; its
`include_paths=True` option and `find()` preserve distinct paths.
Relative custom roots are resolved at discovery time. External paths remain
absolute so later review cannot confuse a working-directory path with an
unrelated file under this repository.

| Review status | Returned matches | Meaning |
|---|---|---|
| `selected` | Only the retained candidates, in model order | Advisory relevance assessment |
| `abstained` | Empty | The model explicitly returned `0` |
| `unavailable` | Original lexical shortlist | No local backend, incomplete input, model error or invalid answer; inspect `reason` |

Malformed answers are rejected as a whole. Numbers embedded in prose or mixed
with out-of-range values are not accepted as a usable review. Repeated valid
numbers are deduplicated while preserving order.

## Inputs, consequences and reuse

The reader limits total instruction bytes to 64 KiB. It rejects missing, empty,
invalid UTF-8 or over-budget bodies before calling the model. It does not send
a truncated body and label it complete. The limit counts source bytes, not the
whole serialized prompt or model tokens; model context errors remain possible.

`local_review.instruction_sha256` records the exact bytes read, including the
frontmatter. On unavailable preparation it can contain only the bodies read so
far. Recheck source hashes and task context before reusing advice. These are
snapshots and do not prove that the model understood the instructions.

The local endpoint receives task text, source paths and full bodies. This uses
the existing local-backend configuration and error handling. It can consume
local inference resources; the zero-cloud-token field does not measure those
costs. There is no new provider, cloud fallback, execution command, memory write
or automatic promotion of a selection into an executable plan.

Referenced files are not loaded or followed by the reviewer. Before using a
candidate, the task agent must read its relevant referenced instructions and
check operation-specific applicability, exclusions and prerequisites. Neither
the model's choice nor a passing instruction hash grants authority.

## Validation scope

Run the existing lexical tests and the new protocol regressions:

```bash
python -m skills.skill_finder.test_skill_finder
python -m skills.skill_finder.test_review
```

The protocol suite creates two skills with the same name in separate roots and
injects model replies. It checks path identity, retained subsets, ordering,
abstention, malformed replies, full input bodies and unavailable-input behavior.
It also checks relative external roots, repository-path collisions and an empty
shortlist, which is unavailable review rather than model abstention.
No real local model is called. These fixtures validate response handling and
input delivery; they cannot establish model selection accuracy or rank model
candidates on real tasks.

Compare the same injected replies against two trusted local checkouts:

```bash
python scripts/evaluate_skill_review.py --baseline /path/to/baseline --candidate .
```

This command imports each checkout in a separate process, creates temporary
fixture skills, and prints a JSON report. It never invokes a real model or a
selected operation. Both source snapshots and the replay script are hashed;
`sources_match_commit=false` identifies a modified working tree. The report
compares three path-selection invariants and full-body delivery. Prompt bytes
are a payload measurement, not a token bill or model-performance result.

The [initial replay record](validation/skill-review-replay-v1.json) compares
baseline `6651335` with the candidate source hashes: all three path invariants
failed before the correction and passed afterward. Full bodies were attached
in all three candidate calls. The fixture prompt grew from 235 to 1,041 UTF-8
bytes; actual local-model cost and task quality remain unmeasured. The candidate
was an uncommitted source snapshot when this record was produced, explicitly
marked in the report, rather than a separately published historical commit.

For a representative comparison, keep a separate, reviewed task set covering
appropriate operations, exclusions, missing prerequisites and irrelevant names.
Freeze source versions and context, compare both versions on the same inputs,
and measure end-to-end task acceptance and actual inference cost. The existing
`tool_router` benchmark covers tool names and argument schemas; `trajectory`
covers routing decisions. This change adds regression coverage to the existing
skill review, without introducing a second runtime router or claiming either
benchmark already measures full skill applicability.

Apply the [six improvement axes](tool-improvement-axes.md) when interpreting
these results. The general representative-task comparison remains open.
