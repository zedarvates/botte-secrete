# Parcimonia: plans guided by the user's conditions

Status: opt-in prototype. Compare supplied candidate plans; no plan generation,
execution, learning, model call, automatic recording or network collection.

The user may request a ranking recommendation or a set of plan proposals to
choose from. A recommendation does not select a plan for the user.

The user defines success for one or several projects and chooses which costs
matter first. This extends the existing Conductor with a separate comparison
operation. Existing execution plans, permissions, checkpoints and routing are
unchanged. The new request is not a `botte.skill-plan/v1` execution document.

The [dated validation record](validation/parcimonia-plan-preferences-2026-11-01.json)
binds the original comparator to its tested source files and limits. The
[proposal follow-up record](validation/parcimonia-plan-proposals-2026-11-01.json)
covers the later multiple-choice operation.

## Try the comparison

From a checkout containing this candidate:

```bash
python -m skills.conductor.cli --compare-plans examples/parcimonia_plan_preferences.json --json
python -m skills.conductor.cli --propose-plans examples/parcimonia_plan_preferences.json --json
```

The local MCP runtime exposes `compare_plans` and `propose_plans`, discoverable
through `find_tool` with the corresponding name. Their only argument is `request_json`, the
UTF-8 JSON document as a string. The separately installed Codex plugin runtime
must contain this code before that tool is available. This change is not an
OpenAI marketplace acceptance, runtime update or production deployment.

Python callers use
`skills.conductor.preferences.rank_plans(request)` or
`propose_plans(request)` after `parse_request_json(text)` when parsing text.

The CLI reads one explicit file and prints JSON. It rejects execution, save and
checkpoint flags in this mode. Exit 0 means at least one known eligible candidate
was ranked or offered, 2 means no candidate can currently be offered, and 1 means invalid or
unreadable input. CLI argument errors use argparse's exit 2 with an error on
stderr. A ranking or proposal does not execute any steps. The two CLI operations
are mutually exclusive; proposal mode has the same file and execution guards.

## Multiple choices for the user

`propose_plans` returns `parcimonia.plan-proposals/v1` using the same strict
`plan-preferences/v1` request as the comparator. It presents every eligible
candidate in ranking order, with its steps, costs, project completion times,
unknowns and Pareto membership. The recommendation is advisory:

| Field | Meaning |
|---|---|
| `recommended_candidate_id` | Best known eligible candidate under the supplied priorities |
| `options` | All currently eligible choices; a lower-ranked or dominated option remains visible |
| `selected_candidate_id` | Always `null`; no user decision is inferred |
| `selection_status` | Always `not_selected`, including ties or a single available option |
| `unavailable_candidates` | Rejected and undetermined alternatives with their retained reasons |

An illustrative user-facing presentation can show a faster plan, a cheaper
plan and their tradeoffs, then let the user choose one or revise their priorities.
The costs are estimates or observations as declared by the caller; the host
must not present them as guaranteed outcomes. If only one candidate qualifies,
present that fact without fabricating a second choice. If none qualifies,
show the missing information or exceeded limits instead of a selectable plan.

The host can collect the user's choice in conversation. That choice should be
associated with the candidate ID and input digest; if goals, costs, limits or
steps change, refresh the proposals before reusing the choice. No selection
ledger or additional execution pipeline is introduced here. An existing mandate
to choose or execute remains a separate host responsibility; offering choices
does not impose a new approval gate on other workflows.

## Versioned request

The [complete example](../examples/parcimonia_plan_preferences.json) describes
two projects with shared work and alternative rapid/economical plans.
The root requires these fields, rejecting other keys:

| Field | Contract |
|---|---|
| `schema` | `parcimonia.plan-preferences/v1` |
| `currency` | One declared uppercase currency code for all `money` values; no conversion |
| `projects` | Objects with unique `id` and required `goals` identifiers |
| `actions` | Canonical objects with `id`, `needs`, beneficiary `projects`, `metrics`, `provenance` |
| `candidates` | Objects with unique `id`, ordered unique `steps`, and declared `goals` per project |
| `preferences` | Ordered `priorities`; optional global `limits` and `project_limits` |

Each action supplies all six metrics, with a non-negative number or `null` for
unknown. Finite inputs and limits are bounded to 10**15. `provenance` contains
`kind` (`estimate` or `measurement`) and a reference in `ref`. Both are caller
declarations, not authenticated observations.

| Metric | Global aggregation | Project aggregation |
|---|---|---|
| `elapsed_minutes` | Sum of serial action durations | Completion time of its last action, including earlier waits |
| `human_minutes` | Sum of declared human effort | Sum for its beneficiary actions |
| `money` | Sum in the one declared currency | Full cost of its beneficiary actions |
| `tokens` | Sum of declared tokens | Sum for its beneficiary actions |
| `energy_wh` | Sum of declared electrical energy | Sum for its beneficiary actions |
| `peak_ram_gib` | Maximum declared peak, with no overlap | Maximum for its beneficiary actions |

Human effort and elapsed time are separate. Electrical energy is not inferred
from tokens, duration or model size. Monetary inputs must cover the same costs;
token counts must use a comparable accounting convention. Unknown measurements
stay `null`. This prototype models serial actions only, with resource release
between steps; persistent processes, parallel schedules and shared live memory
need a later scheduling model and current execution-time resource checks.

An action shared by two projects has one canonical ID and two beneficiaries;
the global budget counts it once. Project budgets each include its full cost,
a conservative attribution rule rather than a division or extra global charge.
Candidates cannot repeat an action ID: intentional repeated work needs distinct
IDs. Source/contract changes also need a fresh action identity and revalidation.

A priority is `{"metric":"elapsed_minutes","project":"demo"}` for a
project-specific criterion, or `{"metric":"money"}` for the whole portfolio.
Criteria are minimized lexicographically in the supplied order. This makes
"finish demo first, then save money" different from "save money, then finish
demo" without inventing a conversion between minutes and euros. Global and
per-project hard limits are applied before ranking; a good preference score
cannot compensate for an exceeded limit. Project urgency can be expressed as
a project completion priority or an `elapsed_minutes` project limit.

## What the result establishes

`parcimonia.plan-ranking/v1` preserves totals, project totals, rejected reasons,
missing required measurements, ranking and the Pareto frontier over active
priorities. A candidate dominated on all active criteria is not a better
tradeoff under those criteria. Stable IDs break ties reproducibly.

Each candidate retains at most 64 diagnostic reasons. `reason_counts` counts
all causes, including omitted ones, and `reasons_omitted` makes truncation
explicit. Eligibility and unknown-action handling use the full evaluation,
so a bounded diagnostic does not hide a rejecting condition. The cap prevents
invalid dense dependency graphs from expanding into millions of report rows.

Dependencies must occur earlier in the candidate. Missing steps, unmet declared
goals and invalid dependency orders reject that candidate. Unknown costs on a
priority or budget produce `undetermined`, not zero cost or proven impossibility.
Unknown metrics unrelated to the active priorities/limits remain visible and do
not automatically block ranking.

The winner is the best **known eligible supplied candidate under the declared
profile**. Undetermined candidates remain visible and may later beat it.
Goal coverage is structural caller data; it does not prove that the actions
will achieve those goals, that estimates are accurate, or that a plan is safe
or authorized to execute. The result does not establish universal optimality.

The canonical input digest binds the profile and candidate data. Reordering
catalogues and set-like memberships preserves it; changing action order,
priorities, costs, references or goals changes it. A digest supports comparison
and replay, not provenance authentication.

## Planning, orchestration and future robotics

The same objective/resource model can apply to software work and robot missions.
The responsibility of each layer must remain explicit:

| Layer | Responsibility | Current status |
|---|---|---|
| Plan comparison | Compare declared alternatives against user goals and budgets | This opt-in prototype |
| Orchestration | Dispatch admitted tasks, follow actual results and replan after changes | Existing Conductor; no automatic dispatch from this comparison |
| ROS navigation | Compute and follow a concrete route using the robot's observed state | Future adapter, not implemented or qualified here |
| Arm and servo control | Fine trajectories, calibration and motor commands | Deferred until the user has the required parts |

For a future robot mission, a candidate may describe visiting work areas in a
particular order, with declared time, human assistance and battery energy costs.
Changing the user's urgency or energy allowance can change the preferred order.
This serial comparison neither computes a collision-free geometric path nor
establishes that a robot can execute it. Map, localization, obstacles and actual
platform capabilities belong to the navigation subsystem's checks.

The future integration should use goal identity, progress, a terminal result,
cancellation and explicit reconciliation after interruption. ROS 2 actions
already provide a goal/feedback/result interface for long-running tasks; Nav2
uses `NavigateToPose` for navigation requests. See the primary
[Nav2 ROS 2 concepts](https://docs.nav2.org/jazzy/getting_started/navigation_concepts/ros2/)
and [NavigateToPose interface](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/bt_plugins/actions/NavigateToPose/).
These references describe the interface pattern, not a distribution selection
or evidence of a working ROS connection in this project.

No ROS node, robot connection, servo movement or fine-motion implementation is
added. The immediate research scope is high-level objectives, task order and
resource tradeoffs; an adapter will be a separate versioned integration when
the hardware and task contracts are available.

## Research during real use

First test the mechanism on the supplied fixture: changing only the preference
order should change the winner, shared work should not double global costs,
and RAM limits should exclude an otherwise attractive plan. These tests validate
the mechanism, not an efficiency gain on real projects.

For practical evaluation, keep the existing [six-axis acceptance method](tool-improvement-axes.md)
and [verified execution records](verified-skill-runs.md). Freeze the request and
code revision; compare the current simple planning method with this candidate
on the same accepted goal, resources and budgets. Measure planning overhead,
execution, verification and retries through the accepted result. Keep failures
and uncertain attempts. Check actual results against their task-specific
verifier before assigning success; a comparison result is not execution evidence.

The existing `skills.trajectory.outcome.emit_outcome` interface can retain
explicit local outcomes with evidence references, tool versions, elapsed time,
tokens, RAM and electrical energy when measured. Its money field is USD: retain
another currency in the comparison artifact rather than silently treating it as
USD. Missing quantities stay unknown. This prototype does not call that recorder
or alter a user's preferences or routing automatically.

Records stay with the user. A user may deliberately share a minimal feedback
example or reproducible failure with a maintainer of their choice. Inspect IDs,
references and supplied project data before sharing: the comparison report is
not an anonymizer. No collector, upload endpoint or automatic export is added.
Provider-side settings and telemetry are separate from this local operation.

The [ETH announcement of 26 October 2026](https://openai.com/index/building-scientific-understanding-with-academic-communities/)
motivates research into combinatorial search. This prototype
uses a bounded deterministic comparison of supplied candidates and makes no
claim to implement the new ETH algorithm or obtain its asymptotic bounds.
Additional dimensions such as reliability, quality thresholds, availability,
storage and permitted data locations remain design work, not silent additions
to this strict v1 contract. The repository's existing `LICENSE` is unchanged.
