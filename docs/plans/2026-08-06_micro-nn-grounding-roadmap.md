# Micro-NN Grounding Roadmap

Status: active  
Owner: Botte Secrete maintainers  
Rule: do not add or activate another micro-NN until the existing inventory has
an auditable label source and a production validation gate.

## Why this roadmap exists

`nn_audit` currently finds eleven wired micro-NN models. Four have reproducible
curated-corpus trainers and test guards. Seven Belt 2.0 predictors have weights
and call sites, but no trainer discovered by the audit, no test guard, and model
metadata that reports `accuracy: 0.0`. Repeated rule-generated feature vectors
or a `trained_on` string are not real grounding evidence.

This roadmap prevents two failure modes:

1. adding more tiny models while existing ones still lack real verdicts;
2. allowing a synthetic or unknown predictor to become a silent policy engine.

## Maturity levels

| Level | Meaning | Decision authority |
|---|---|---|
| G0 | Unknown, synthetic, or unreproducible weights | Shadow only |
| G1 | Versioned corpus, label contract, holdout, provenance, test guard | Advisory |
| G2 | Real production observations with deterministic or explicit verdicts | Staged |
| G3 | Calibrated, drift-monitored, rollback-tested production model | Active |

A model is not "finished" before G2. Security checks, exact validation, budget
limits, and destructive-action policy remain deterministic even at G3.

## Current inventory and exit gates

Snapshot command:

```bash
python -m skills.nn_audit.cli skills/botte_nn --json
```

| Model | Current | Real label source | Minimum G2 gate | Next action |
|---|---:|---|---|---|
| `binary_router` | G1 + shadow collection | `route_feedback` verdicts | 2,000 verified; both classes represented; calibration and rollback pass | Continue real verdict collection |
| `effort_classifier` | G1 | reviewed task tier plus successful execution | 2,000 verified; macro-F1 beats heuristic baseline | Add shadow outcome collector |
| `anomaly_detector` | G1 | confirmed incident/anomaly resolution | 1,000 verified windows; bounded false-negative rate | Link alerts to incident verdicts |
| `error_classifier` | G1 | real exception type and recovery result | 1,000 verified errors; macro-F1 >= 0.90 | Persist provenance in exported weights |
| `compressibility_predictor` | G0, collector active | exact roundtrip plus measured reduction | 1,000 automatic labels across text, JSON, code, and logs | Accumulate diverse reversible calls, then temporal holdout |
| `semantic_cache_hit_predictor` | G0, collector active | actual cache hit or miss | 2,000 automatic labels; temporal holdout | Accumulate real lookups and monitor class balance |
| `cloud_escalation_predictor` | G0 | verified local/harness/cloud outcome | 2,000 verified; prove incremental value over `binary_router` | Merge or remove if redundant |
| `context_pruning_predictor` | G0 | matched full-context versus pruned evaluation | 500 matched pairs; no material quality regression | Build replay evaluator |
| `skip_agent_predictor` | G0 | matched execute versus skip replay | 500 matched pairs; fail-open to execute | Build no-change oracle and replay |
| `tool_call_predictor` | G0 | task success with reviewed tool requirement | 1,000 verified; false-negative guard for required tools | Collect tool-use outcomes |
| `response_length_predictor` | G0 | truncation, user preference, and task acceptance | 1,000 verified; no truncation regression | Add explicit length feedback |

Sample counts are minimum activation gates, not targets to satisfy by duplicating
cases. Duplicated prompts, repeated feature vectors, and labels copied from the
current rule are excluded from the verified count.

## Execution order

### Wave 0 - fail closed and make evidence auditable

- Add a machine-readable provenance manifest and label contract for all models.
- Keep G0 models in shadow mode; deterministic policy remains authoritative.
- Record dataset fingerprint, split strategy, class balance, metrics, and date.
- Make `/checkup` report G0/G1/G2/G3 rather than trusting model metadata alone.

### Wave 1 - deterministic labels first

Ground models whose outcomes already have exact local oracles:

1. `compressibility_predictor` from roundtrip and measured reduction;
2. `semantic_cache_hit_predictor` from actual cache outcomes;
3. `error_classifier` from exception classes and recovery results.

These produce honest labels without cloud tokens or subjective review.
The first two collectors are active: they append calibrated, verified labels,
deduplicate stable fingerprints, and never persist raw content or queries.

### Wave 2 - routing and operational verdicts

Continue `binary_router`, then instrument `effort_classifier`,
`anomaly_detector`, and `cloud_escalation_predictor`. Compare the escalation
predictor against the simpler binary router and remove it if it adds no measured
value.

### Wave 3 - causal or human-reviewed labels

Use bounded replay or explicit feedback for context pruning, agent skipping,
tool use, and response length. These models must not learn from "what the current
policy did" because that would only clone existing mistakes.

## Future candidates - frozen

Do not implement these before the existing eleven reach G2 or are removed:

| Candidate | Preferred first baseline | Why it may help later |
|---|---|---|
| `harness_risk_predictor` | deterministic harness outcomes | Predict local verification failure; verifier remains authoritative |
| `local_backend_selector` | contextual bandit plus measured latency | Choose host/model under RAM, context, latency, and quality constraints |
| `test_scope_predictor` | dependency graph and changed-file rules | Recommend targeted tests without bypassing the release suite |

Malware verdicts, permission policy, destructive actions, budgets, archive
lifecycle, syntax checks, and exact solvers are explicitly excluded from micro-NN
authority.

## Definition of done

- Every retained model is G2 or G3 and has a named consumer.
- Every label has provenance and a deterministic or explicit-verdict contract.
- Training, calibration, holdout evaluation, rollback, and drift checks reproduce.
- `/checkup` reports no unknown, synthetic-active, or orphan model.
- A measured ablation shows each model beats its deterministic baseline or it is
  merged/removed.
- Only then may a frozen future candidate enter a shadow-only experiment.
