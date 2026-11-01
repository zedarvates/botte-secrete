# Parcimonia: uncertain costs and useful measurements

Status: opt-in deterministic analysis. The existing
[comparison/choice request](parcimonia-plan-preferences.md) stays unchanged.
These helpers do not select a plan, ask a question, perform a measurement,
execute work, call a model, save data or contact a network.
The [dated validation record](validation/parcimonia-plan-uncertainty-2026-11-01.json)
binds current sources, the illustrative decision case and reuse of the retained
pilot's observed ranges. Those observed min/max values are not future bounds
or statistical confidence intervals.

## Supply declared ranges

```bash
python -m skills.conductor.cli --analyse-plan-uncertainty examples/parcimonia_plan_uncertainty.json --json
python -m skills.conductor.cli --suggest-plan-measurements examples/parcimonia_plan_uncertainty.json --max-checks 8 --max-questions 3 --json
```

The local MCP tools have the corresponding names `analyse_plan_uncertainty`
and `suggest_plan_measurements`. Both take `request_json`; the latter also
accepts `max_checks` and `max_questions`. They are lazily discoverable through
`find_tool`. Python uses `skills.conductor.uncertainty.analyse_plan_uncertainty`
and `skills.conductor.measurement.suggest_plan_measurements`.

The `parcimonia.plan-uncertainty/v1` envelope requires exactly:

| Field | Meaning |
|---|---|
| `schema` | `parcimonia.plan-uncertainty/v1` |
| `comparison_request` | Complete existing `parcimonia.plan-preferences/v1` input |
| `ranges` | Unique action/metric ranges with `action_id`, `metric`, `lower`, `upper`, `provenance` |

Range provenance is `{kind: estimate or measurement, ref: supplied reference}`.
Endpoints must be finite nonnegative numbers at most 10**15, with lower no
greater than upper. A known nominal value must lie inside its declared range.
Missing or null endpoints are rejected; a fully unknown cost is represented
by a null nominal metric with no range. All data remains unverified caller
declarations. The complete envelope is bounded to 1 MiB of strict UTF-8 JSON.

Without a range, a supplied number is treated as a point value for this model;
that assumption does not make an estimate a guaranteed real cost. A null remains
unknown in the nominal comparison. For interval arithmetic only, nonnegativity
implies a domain lower bound of zero and an unknown upper bound. This zero is
not a measurement or a replacement point estimate. `fully_unknown_costs` and
`bound_assumptions` preserve this distinction explicitly.

The supplied illustrative example prioritizes elapsed time under a spending
limit. Its nominal recommendation is `rapid`, but the declared time/cost
ranges do not certify that choice. Endpoint probes identify the duration of
`fast-demo` and the spending of `fast-demo` / `fast-plugin` as decision-sensitive.
These figures are synthetic declarations, not measured project performance.

## Read conditional robustness

`parcimonia.plan-uncertainty-report/v1` retains nominal advice, lower/upper
global and project totals, structural status, budget status and required
priority values. Aggregation uses the same serial completion times, full
beneficiary project attribution, global deduplication and maximum RAM as the
existing comparator.

A candidate is within the declared limits only when all relevant upper bounds
are known and fit. A lower bound already over a limit proves that supplied
candidate cannot fit that declared budget. Straddling or unbounded costs leave
budget feasibility uncertain. Structurally rejected candidates stay rejected;
their structural reasons must be read before interpreting budget advice.

A `robust_recommended_candidate_id` is a conservative certificate: that plan's
worst declared priority vector still ranks ahead of every possible rival's
best vector, using the same lexicographic priorities and stable ID tiebreak.
It must also satisfy its upper-bound budgets. Unknown required priorities
prevent certification. The check is sufficient, not necessary: shared costs
can be correlated, so independent extremes can reject a certificate that a
more exact joint analysis could establish.

This statement applies only to the supplied plans, declared ranges and current
cost model. It is not a probability, confidence interval, proof of the ranges,
real-world feasibility or global optimality. No certificate does not mean a
plan is impossible. `selected_candidate_id` stays null even when a certificate
exists; nominal and robust recommendations remain advisory.

`apply_range_values(envelope, bound)` is a separate Python helper for explicitly
projecting supplied `lower` or `upper` values into a fresh comparison request.
Unbounded nulls stay null. Touched actions are labeled `estimate` with a
reference to the envelope digest and chosen bound; projected hypothetical
endpoints are never relabeled as observations. Using a projected request for
choice is a deliberate change of policy and input digest, not an automatic
override of existing selection rules.

## Suggest measurements without pretending to know their value

`parcimonia.plan-measurements/v1` probes one action metric at a time, setting it
to each endpoint while every other cost remains nominal. It identifies changes
in the recommended candidate or eligibility, then lists required unknown costs.
Only variables feeding a priority or budget are relevant. Project completion
time correctly includes earlier actions from other projects; shared variables
are not duplicated per beneficiary or candidate.

The hint order is deterministic: detected recommendation changes, eligibility
changes, then required unknowns. This is endpoint sensitivity, not an expected
value of information calculation. It knows neither measurement cost nor outcome
probabilities, and cannot promise to find the cheapest or most useful question.
Several uncertainties can interact even when no single endpoint probe changes
the choice. `joint_uncertainty_evaluated` stays false; the separate conservative
certificate is the only reported stability certificate.

`max_checks` limits variable probes to 1..128 (default 32), with two rank calls
per checked variable. `max_questions` limits displayed hints to 1..16 (default
8). Omitted variables, incomplete analysis and omitted questions remain explicit.
Completeness refers to the chosen one-factor procedure, not exhaustive joint
exploration. Required unknowns remain indexed even when their question details
are not displayed; detail samples and omission counts keep reports bounded.
`unresolved_required_unknowns` is the exhaustive compact action/metric index.
`unresolved_required_unknown_contexts` retains at most 64 detailed contexts;
the total count, omitted-context count and truncation flag remain explicit.
Unretained unknown questions do not construct full contexts merely to discard
them later.

The host may use a hint to ask the user or perform an appropriate authorized
measurement. The helper itself dispatches neither. It never silently changes
the user's priorities, pretends an estimate was measured or grants execution.
These CLI modes are mutually exclusive with other planning document modes and
reject execution/checkpoint flags. Measurement limits are rejected outside the
measurement-suggestion mode. Successful analysis exits 0 even when uncertain;
invalid documents exit 1 and argparse argument errors exit 2.
