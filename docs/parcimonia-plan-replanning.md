# Parcimonia: review remaining work against current evidence

Status: opt-in local, read-only advice. The reviewer uses an existing Conductor
checkpoint and the original [selection/handoff](parcimonia-plan-preferences.md).
It compares the supplied current candidates after checking which completed
results remain reusable. It does not select, execute, retry, migrate a checkpoint
or grant permission. The existing executor and checkpoint schema stay unchanged.

The [dated validation record](validation/parcimonia-plan-replanning-2026-11-01.json)
binds sources and checks. A separate [isolated real pilot](validation/plan-replanning-pilot-2026-11-01.json)
records two worker stages, a precondition block, successful original-plan resume
without repeating the first write, and stale evidence without automatic replay.
This is a correctness demonstration, not a speed, energy or project-quality gain.

## Supply the previous binding and current preferences

Python calls
`skills.conductor.replanning.review_plan_replanning(envelope, checkpoint_path, cwd=".")`.
The CLI uses:

```bash
python -m skills.conductor.cli --review-plan-replanning request.json --project /path/to/project --checkpoint work/checkpoint.json --json
```

`request.json` is supplied by the caller; the checkpoint must already exist
inside the explicitly chosen project. Paths to checkpoints are project-relative;
absolute paths, escapes and paths aliased to observed plan resources are rejected.
The [example envelope](../examples/parcimonia_plan_replanning.json) shows the strict
shape, using synthetic estimates and a supplied original execution plan. It has
no portable checkpoint and cannot certify reuse by itself.

The MCP tool `review_plan_replanning` takes `request_json`, `checkpoint_path` and
optional `cwd` (default `.`). It is lazily discoverable with `find_tool` and has
read-only annotations. CLI execution, resume, save and other planning modes are
mutually exclusive with this review. Here `--checkpoint` names an input file;
it never enables checkpoint writing.

The complete strict UTF-8 JSON envelope is limited to 1 MiB:

| Field | Meaning |
|---|---|
| `schema` | `parcimonia.plan-replanning/v1` |
| `previous_request` | Original complete `parcimonia.plan-preferences/v1` request |
| `previous_handoff` | Original validated `parcimonia.plan-handoff/v1` binding |
| `current_request` | Complete current comparison request, including remaining budgets |
| `budget_scope` | Exactly `remaining_work` |

The previous handoff is revalidated against its request. Checkpoint schema,
immutable execution-plan digest, step IDs/order, state types and runtime context
must match. Context binds the resolved project root, declared plan context,
Python version and executable. A moved project or different runtime needs explicit
reconciliation; this helper does not transfer that identity.

## Read three distinct step states

| State | Evidence required and consequence |
|---|---|
| `reusable` | Started, checkpoint says verified with integer exit code 0, nonempty passing postconditions, passing current preconditions/source hashes, and reusable dependencies. Reuse for the current request also requires an unchanged action contract. |
| `unstarted` | Explicit `started: false`, null exit code, and pending/blocked/skipped status. It remains work to do; the reviewer does not dispatch it. |
| `reconciliation_required` | Started work is unresolved, evidence is stale, dependencies cannot be reused, or a present current action changes its contract. The reviewer does not turn this into retryable work. |

The action contract binds ID, dependency set, beneficiary-project set and
provenance. Declared metric changes alone are permitted. If an old action is
absent from the current request, the historical evidence can remain locally valid
but cannot provide reuse credit to a current action. A dependency's stale result
prevents downstream reuse even if a downstream file still passes its own check.

Local observations are recalculated from the original plan's declared predicates
and source hashes, not trusted merely because they appear in the checkpoint.
Checkpoint bytes are hashed before and after review; observed checkpoint changes
invalidate the review. This is not an atomic filesystem snapshot. The executor
must check again before resuming, and future changes can invalidate any result.
Content hashes do not authenticate the checkpoint author, command semantics,
goal fulfillment, user authority or external effects.

## Compare the remaining allowances

Only unchanged reusable actions receive zero *future additive* cost for elapsed
time, human time, money, tokens and energy. Remaining actions preserve their
relative serial order. Shared actions count once globally, with full beneficiary
attribution. A project's remaining elapsed time runs through its last remaining
beneficiary action; it is zero when every beneficiary action is reusable, even
if unrelated remaining actions precede it in the original plan. Completed
projects remain in the request and report rather than disappearing with their
goals. Structural checks use the original full candidate order, so the internal
cost calculation cannot repair an invalid dependency order or change the
immutable execution plan.

`peak_ram_gib` retains every action's declared peak, including reused actions.
Completion does not prove processes stopped or memory was freed. Unknown RAM
stays unknown. This conservative aggregate is not a live resource measurement.

Global and per-project limits in `current_request` are caller-supplied **remaining
allowances**. No estimated past expenditure is subtracted from them. Unknown
costs of remaining actions stay unknown. Validation overhead is excluded, so
zero additive future action cost does not mean the review or reuse is free.

The internal adjusted comparison is coupled to the review input, checkpoint and
step checks. It is not returned as a standalone zero-cost request for later
selection or handoff. The original full request, receipt and execution plan
retain their identities.

## Interpret the advisory report

`parcimonia.plan-replanning-report/v1` includes input/checkpoint/context digests,
step states, bounded diagnostics with exact counts, global reconciliation state,
candidate remaining totals, reused/remaining action IDs, ranking and recommendation.
Costs are declared estimates; passing predicates do not measure resource costs.
`detail_caps` declares 64 global diagnostics, 64 reasons per candidate and eight
goal IDs per missing-goals reason. Each sampled goal list has exact `goal_count`
and `goals_omitted`; compaction changes neither rejection nor reason counts.

A candidate that uses an unresolved started action, or transitively depends on
one in the current action graph, is `withheld` and has unknown cost totals.
Independent candidates may still receive advice while global
`reconciliation_required` stays true. Their recommendation never resolves the
old active or uncertain work.

`resume_compatible` states only that the candidate matches the original choice,
step order, goals, projects and action contracts. It is not readiness, permission
or budget feasibility. A withheld candidate's `execution_status` explicitly says
`reconciliation_required`; another incompatible candidate is
`execution_unqualified`. The existing executor may resume only the unchanged
original execution plan with its original checkpoint, under its usual authority
and fresh checks. This helper provides no checkpoint migration or new execution
handoff. `selected_candidate_id` stays null and `execution_authorized` stays false.

Successful review exits 0, including reconciliation outcomes. Invalid input,
checkpoint identity or observed checkpoint changes exit 1; invalid CLI argument
combinations exit 2. No application telemetry collector is added.

## Reproduce the bounded execution demonstration

```bash
python -m scripts.plan_replanning_pilot --output /tmp/replanning-preview.json
python -m scripts.plan_replanning_pilot --run --output /tmp/replanning-run.json
```

Each output path must be new. The default previews without subprocess execution.
`--run` explicitly runs only the fixed temporary-file demonstration through the
existing Conductor executor. It retains failures, source identities, checkpoint
hashes and write counters, then removes the temporary project. Its checkpoint
cannot be resumed after cleanup. The initial stop is an unstarted precondition
block, not a real process interruption; interrupted and uncertain states also
have separate regression fixtures. No robot, network service, model or production
resource is invoked by this worker.

The separate [sharing analysis](parcimonia-plan-synergies.md) compares explicitly
supplied cross-project alternatives. Automatic semantic sharing discovery, human
availability, explicit scope reductions and local calibration remain further
work. ROS navigation and fine robot movements are not implemented or qualified
by this review.
