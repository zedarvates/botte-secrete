# Parcimonia: compare declared sharing between projects

Status: opt-in, deterministic advice. The existing
[recipe builder](parcimonia-recipe-planning.md) already constructs combinations
using canonical shared action IDs. This analysis compares supplied full
separate/shared candidates under an explicit sharing assumption. It explains
global and per-project tradeoffs without changing actions, dependencies,
priorities, costs or candidates.

The [dated validation record](validation/parcimonia-plan-synergies-2026-11-01.json)
binds source versions and checks. The [isolated real pilot](validation/plan-synergy-pilot-2026-11-01.json)
verifies a fixed two-project preparation shared once, with both final results
checked independently. That case does not establish general performance gains.

## Declare a comparison

```bash
python -m skills.conductor.cli --analyse-plan-synergies examples/parcimonia_plan_synergies.json --json
```

Python uses `skills.conductor.synergies.analyse_plan_synergies(envelope)`.
The lazily discoverable MCP tool `analyse_plan_synergies` accepts only
`request_json`. The helper performs no file access, model call, measurement,
question, selection or execution. CLI execution, save, checkpoint, resume and
other planning document modes cannot be combined with this analysis.

The strict UTF-8 JSON envelope is bounded to 1 MiB:

| Field | Meaning |
|---|---|
| `schema` | `parcimonia.plan-synergies/v1` |
| `comparison_request` | Complete existing `parcimonia.plan-preferences/v1` request |
| `opportunities` | Up to 32 explicit sharing comparisons |

Each opportunity requires exactly:

| Field | Meaning |
|---|---|
| `id` | Unique opportunity ID |
| `baseline_candidate_id` | Supplied separate-work candidate |
| `shared_candidate_id` | Distinct supplied shared-work candidate |
| `separate_action_ids` | At least two unique source actions in the baseline |
| `shared_action_id` | One supplied common action in the shared candidate |
| `assumption_ref` | Caller reference for the sharing assumption, 1..512 characters |

Both candidates must exist and declare the same goals per project. The baseline
must contain all separate actions and exclude the common action; the shared
candidate must contain the common action and exclude every separate action.
The common action must benefit exactly the union of the separate actions'
beneficiary projects, involving at least two projects. Unknown IDs, duplicate
bindings and contradictory declarations are input errors.

These checks bind the comparison; they do not prove that the common action
provides equivalent results. `assumption_ref` is untrusted caller data, not an
instruction or retrieved evidence. Similar names, commands or outputs never
cause an implicit merge. Explicit shared costs and provenance come from the
existing action catalogue; the helper does not invent a zero-cost action.

One action ID has one canonical contract across all candidates. If a consumer
uses different prerequisites in the shared alternative, supply a distinct
consumer ID with that dependency contract. This preserves the baseline. The
helper never rewrites an existing action's `needs` or generates commands.

## Read whole-plan differences and project effects

`parcimonia.plan-synergies-report/v1` retains the original ranking and candidate
statuses. Each opportunity compares its two full candidates, including every
other action and order difference. The added/removed action inventories make
those differences visible. A lower whole-plan cost does not establish that
sharing alone caused the reduction; `attribution_to_sharing_verified` is false.

`global_delta` and `project_deltas` use **shared minus baseline**. A negative
known value is a lower declared cost; a positive value is higher. If either
side is unknown, the difference stays null. Differences are computed with exact
Decimal aggregates before conversion to public JSON numbers. If a number loses
precision during publication, `delta_rounding.global`, `.projects` or `.group`
retains an integer index into the report's `exact_delta_values` table of exact
signed decimal strings. Identical exact values share one table entry. For
example, a nonzero difference below the smallest representable float may
display as `-0.0`; its exact companion preserves the decrease. Empty companion
maps mean no difference was lost in that scope. `delta_publication` explains
this convention.

`group_metrics` separately totals
only the listed separate actions and the common action. This group arithmetic
excludes their dependencies and other changed actions, so it is not a standalone
feasibility check or a causal savings measurement.

All aggregation follows the existing serial model: additive costs sum, global
shared work counts once, beneficiary projects receive the full attributed cost,
RAM is a maximum, and each project's elapsed time includes the serial prefix
through its last beneficiary action. A common preparation may reduce total work
while increasing a project's attributed cost or delaying an urgent result.
The supplied priorities and global/project hard limits determine eligibility
and recommendation; the sharing label never receives a ranking bonus.

Structural rejection of either candidate makes an opportunity `unqualified`,
with null differences. Budget rejection alone still permits a cost comparison,
with the rejection status and reasons preserved. Required unknown costs can
leave a candidate undetermined. `preferred_eligible_candidate_id` follows the
original ranking within a qualified pair; it is null when no pair member is
eligible. The global recommendation considers all supplied candidates, including
those outside the listed opportunity.

Candidate reasons retain at most eight samples, with at most four goal IDs in
each missing-goal reason and exact counts/omissions. Added/removed inventories
retain at most 32 IDs each with exact counts. The complete report is bounded to
2 MiB in canonical UTF-8 JSON and rejects an oversized result rather than
returning an unbounded report. Output formatting can add whitespace or escapes.
`detail_caps` exposes the limits. Compaction does not change eligibility or rank.

## Keep choice, execution and evidence distinct

`input_digest` binds the comparison digest and canonical opportunity declarations.
`comparison_input_digest` remains the digest of the unchanged original comparison
request. Opportunity order and member-set order are canonicalized; candidate
serial order and user priority order retain their meaning.

After the user chooses, the existing `select_plan` operation consumes the
original `comparison_request` and `comparison_input_digest`. Its receipt binds
that comparison, while the synergy report separately binds the sharing
assumptions. Commands and checks still come from the trusted controller through
the existing [handoff](parcimonia-plan-preferences.md). A synergy annotation
neither qualifies command semantics nor migrates a checkpoint.

`selected_candidate_id` stays null and `execution_authorized` stays false.
The report does not authenticate source provenance, equivalent outcomes,
goal coverage or authority. Unknown consumption stays unknown; review overhead,
unlisted costs and live resource use are not measured.

Successful analysis exits 0, including unqualified or rejected alternatives.
Malformed input exits 1; incompatible CLI arguments exit 2.

## Reproduce the fixed local pilot

```bash
python -m scripts.plan_synergy_pilot --output /tmp/synergy-preview.json
python -m scripts.plan_synergy_pilot --run --output /tmp/synergy-run.json
```

Output paths must be new. The default previews without subprocesses. `--run`
permits only the fixed demonstration, through existing Conductor gates in
isolated temporary projects. Both variants have supplied commands and independent
expected-result checks. Source identities, preparation counters, final results
and failures are retained; temporary projects are removed afterward.

Observed preparation counts qualify this fixed worker and input. Timings are
observations with their recorded scope, not forecasts or evidence of general
time, token or energy gains. This work does not add central telemetry, ROS
navigation, motor control or automatic semantic sharing discovery.
