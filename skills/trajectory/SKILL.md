---
name: trajectory
description: Store solver history and maintain a project-local Quality Compass that learns only from externally verified outcomes. Use when a task needs explainable k-NN recall, qualitative QA labels, a shadow routing baseline, or evidence collection before training a micro-NN.
license: MIT
---

# trajectory — verified memory and Quality Compass

This skill has two deliberately separate lanes:

| Lane | Purpose | Authority |
|---|---|---|
| Legacy solver history | Recall prior deterministic solver results | Informational |
| Quality Compass | Compare a task with externally verified outcomes | Shadow-only advisory |

The Quality Compass is the default path for new QA and routing work. It gives a
simple k-nearest-neighbor baseline before another micro-NN is considered.

## One-command flow

```bash
botte qa                                      # status + one next step
botte qa "summarize this failing test log"   # shadow advice shortcut
botte qa advise "summarize this log" --task-type summary --json
botte qa record "summarize this log" \
  --route local --verdict pass --verified-by tests:pytest \
  --duration-ms 180 --tokens 140 --evidence pytest:test_logs
```

`botte qa <task>` is intentionally equivalent to `botte qa advise <task>`.
Advice always says why it suggested, abstained, or invoked a human gate. It
never executes the route.

## Python API

```python
from skills.trajectory import advise_route, quality_status, record_verified

record_verified(
    "summarize parser failures",
    project_root=".",
    route="local",
    verdict="PASS",
    verified_by="tests:pytest",
    evidence_refs=("pytest:test_parser",),
)

advice = advise_route("summarize another parser failure", project_root=".")
print(advice.to_dict())
print(quality_status("."))
```

Execution paths should use the bounded envelope adapter instead of calling the
verified ledger directly:

```python
from skills.trajectory import emit_outcome

emit_outcome(
    "summarize parser failures",
    project_root=".",
    execution_id="ci-run-42/job-3",  # hashed, never stored verbatim
    source="ci",
    route="local",
    status="PASS",
    verified_by="ci:pytest",
    evidence_refs=("pytest:test_parser",),
    harness="local-extract-v1",
)
```

The envelope accepts partial facts and lifecycle states (`PARTIAL`, `FAIL`,
`UNCERTAIN`, `PASS`, `PASS_ROBUST`, `ABSTAINED`, `ESCALATED`, and
`APPROVAL_REQUIRED`). It writes a private, idempotent status row. A verdict is
promoted to the k-NN support ledger only when both an allowed external verifier
and at least one evidence reference are present. Replaying the same execution
and outcome returns the existing row and cannot add another label.

The local harness is the first live adapter. Deterministic schema, grounding,
and citation checks can produce verified `PASS`, `FAIL`, or `UNCERTAIN` labels;
gates, abstentions, and escalation remain explicit without treating the final
unverified model answer as evidence. Router, Codex/Hermes, CI, and Kanboard
adapters remain follow-up integration points.

## Quality contract

- Valid verdicts: `FAIL`, `UNCERTAIN`, `PASS`, `PASS_ROBUST`.
- Valid routes: `deterministic`, `local`, `cloud`, `human`.
- Labels require an external verifier such as tests, schema validation,
  deterministic roundtrip, replay, human review, independent review, or a
  benchmark. A model/backend self-report is rejected.
- Raw task text is never written to the quality ledger. Botte stores a SHA-256
  fingerprint and a normalized 128-dimensional sparse hashed feature vector.
- Repeated copies of the same task/route do not inflate grounding progress or
  k-NN support.
- High/critical risk bypasses k-NN and retains a human approval gate.
- The baseline is uncalibrated and shadow-only. It cannot activate routing.
- At 2,000 non-duplicated verified outcomes, the next step is evaluation:
  temporal holdout, calibration, ablation, drift, and rollback — not automatic
  deployment.

The k-NN chooser selects the least expensive observed route whose similar
support clears the quality floor. If evidence is sparse or conflicting, it
abstains and leaves the deterministic router in control.

## Leakage-resistant routing benchmark

Compare the deterministic rule, Quality Compass k-NN, and the existing
`binary_router` micro-NN on one oldest-train/newest-holdout split:

```bash
python -m skills.trajectory.cli benchmark --project . --json
python -m skills.trajectory.cli benchmark \
  --missions private/sanitized-routing-missions.jsonl \
  --code-ref "$(git rev-parse HEAD)" --output benchmark.json --json
```

Without a mission file, the command inventories observable evidence and emits
a machine-readable `collect_more_data` gap report. A mission set must conform
to `docs/schemas/quality-routing-mission.schema.json`, use independent evidence,
contain only sanitized task text, and keep task families disjoint across the
temporal boundary. Fixtures exercise the harness but can never rank candidates.
The output contract is `docs/schemas/quality-routing-benchmark.schema.json`.

The benchmark measures routing-oracle accuracy, coverage, abstention,
disagreement, confidence intervals, decision latency, Python allocation peak,
and calibration where confidence exists. Model-answer and harness-execution
quality remain separate and explicitly unobserved unless independently
verifiable outcomes are supplied. It never executes a model, trains weights,
changes a route, or grants `ACT` authority.

## MCP tools

| Tool | Purpose |
|---|---|
| `qa_status` | Show maturity, support coverage, privacy posture, and next step |
| `qa_advise` | Return an explainable shadow recommendation or abstention |
| `qa_record` | Add one externally verified outcome without storing raw task text |

## Local state

| Path | Content |
|---|---|
| `<project>/.botte/quality-trajectories.jsonl` | Private verified support set |
| `<project>/.botte/quality-outcomes.jsonl` | Private bounded execution/status envelopes |
| `<project>/.botte/events.jsonl` | Compact `qa_outcome`, `qa_trajectory`, and `qa_shadow_advice` events |
| `skills/trajectory/store/trajectories.jsonl` | Legacy solver fixtures/history |

Project-local `.botte/` data is operational state and must not be committed.
The legacy `capture`, `search`, `load`, and `get_stats` API remains available for
existing deterministic solver integrations; do not put secrets in that legacy
store.

## Why k-NN comes before another micro-NN

k-NN updates immediately when a verified example arrives, has no training job,
and can show the exact neighboring outcome IDs behind a suggestion. A compact
micro-NN becomes a candidate only when the support set is large, diverse, and
stable enough to beat this baseline on a temporal holdout without quality loss.
