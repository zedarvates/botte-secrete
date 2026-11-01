# Parcimonia: explicit recipes to alternative plans

Status: opt-in bounded prototype. Recipe construction is a separate operation
from ranking, user choice and Conductor execution. Existing
[comparison and choice contracts](parcimonia-plan-preferences.md) are unchanged.
The [dated validation record](validation/parcimonia-recipe-planning-2026-11-01.json)
binds the source files, construction trial, resource regression and pilot report.

## Build and compare

```bash
python -m skills.conductor.cli --build-plan-candidates examples/parcimonia_recipe_planning.json --json
```

The local MCP tool `build_plan_candidates` accepts one `request_json` string.
It is discoverable through `find_tool`. Python callers use
`skills.conductor.recipes.build_plan_candidates(request)`.
The CLI reads an explicit UTF-8 JSON file and prints the result. It rejects
execution and selection flags; it creates no files or subprocesses. Exit 0
means at least one candidate was built, 2 means no candidate was built, and 1
means malformed/unreadable input. Argument errors use argparse exit 2.

The recipe request schema is `parcimonia.recipe-planning/v1`:

| Field | Contract |
|---|---|
| `currency`, `projects`, `actions`, `preferences` | Same strict definitions as the comparison request |
| `recipes` | Alternative methods, each with unique `id`, requested `project`, requested `goal`, and canonical `actions` IDs |
| `max_candidates` | Optional limit, default 16, range 1..64 |
| `max_expansions` | Optional attempted-combination limit, default 256, range 1..4096 |

The [complete example](../examples/parcimonia_recipe_planning.json) contains two
projects, alternative recipes and shared prerequisites. Input remains bounded
to 1 MiB and strict JSON; costs are caller declarations, not invented estimates.

For each requested project goal, the planner chooses one explicit recipe. It
combines the methods, adds the transitive dependency closure of their actions,
and puts the union in a deterministic serial topological order. Shared work
appears only once. Identical resulting action plans are deduplicated. The
algorithm does not interpret natural-language goals, retrieve wiki pages,
invent missing operations or synthesize executable commands.
Each recipe combination produces one deterministic action order; this version
does not enumerate all possible serial permutations or parallel schedules.

## Read the result

`parcimonia.recipe-candidates/v1` returns:

| Field | Meaning |
|---|---|
| `comparison_request` | Existing `parcimonia.plan-preferences/v1` object ready for `propose_plans`, or null when nothing was built |
| `candidate_recipes` | Recipe IDs responsible for each retained candidate |
| `input_digest` | Canonical identity of the recipe-planning input |
| `search` | Attempted combinations, retained candidates, configured limits and explicit completeness/truncation |
| `diagnostics`, counts and omissions | Missing recipes or failed combinations, within a bounded report |

Use `propose_plans(result["comparison_request"])` when that field is non-null.
The existing user-choice receipt then binds the generated comparison request.
Recipe construction does not select an option or authorize execution. A later
Conductor handoff still needs a separately supplied trusted execution plan.

Missing recipes, dependency cycles and unavailable dependencies cannot be
filled in by assumption. A failed or truncated search does not prove that the
user's goal is impossible. When a search limit is reached, the report preserves
already-built candidates and states that exploration was incomplete. The same
applies when another candidate would exceed the comparison document's size
limit. No global optimum or real-world feasibility is claimed.

Recipe coverage and goal achievement remain unverified declarations. A graph
that has a valid order may still describe an unsuitable method. Reuse requires
the source, current prerequisites and task-specific result verifiers. The
planner's job here is bounded structural construction, not validation of every
recipe's meaning.

## Real isolated verification pilot

The reusable [pilot script](../scripts/plan_validation_pilot.py) compares two
ways to verify an identical fixed set of existing tests: one grouped process
and separate module-group processes. It uses the existing Conductor executor,
with explicit supplied commands, frozen source hashes and checks of the exact
test IDs and results. This is a separate explicit execution from the pure
planning helpers.

The pilot runs local verification commands in an isolated source snapshot and
records complete outcomes, timing and overhead. It makes no model/service/robot
call and does not write to the user's production learning ledger. Tokens,
money, RAM and electricity remain unknown where unmeasured. Equal test coverage
does not establish equal coverage of the whole repository.

By default the script prepares a preview. `--run` explicitly executes the fixed
local pilot; `--output` must name a new report file. For example, from a checkout:

```bash
python scripts/plan_validation_pilot.py --output pilot-preview.json
python scripts/plan_validation_pilot.py --run --output pilot-measurement.json
```

The [retained measurement](validation/plan-validation-pilot-2026-11-01.json)
contains three alternating paired repetitions: all six runs verified the same
12 named tests. Median time to the verified result, including method preparation
and supervising guards, was 0.305859 s for one process and 0.834172 s for four
module-group processes in this environment. The reference method was retained.
The actual comparator's retrospective recommendation was `batched`, with no
candidate automatically selected. Its other five cost metrics stayed null.

The report binds 16 source files, preserves the prior pilot iteration and
accounts for rerun/development overhead separately. The timing comparison does
not claim to predict a future run or qualify all verification work. Running
this pilot later produces a new dated observation, not a replacement for the
retained evidence.

Measured timing characterizes this environment and test set. It is not a
forecast-accuracy benchmark, evidence of a general project-speed improvement,
or a qualification of physical workstations. The report keeps failures and
repeated runs so the next planning improvement can be selected from observed
results rather than a claimed gain.

The separate [cost-range and measurement guide](parcimonia-plan-uncertainty.md)
describes conditional interval comparisons and bounded sensitivity hints.
The separate [remaining-work review](parcimonia-plan-replanning.md) checks an
existing checkpoint and current local evidence before advising on reuse.
Further work includes detecting cross-project synergies, explicit scope
reductions, human availability/attention and user-local calibration. Those
capabilities are not silently added to the comparison schema by this recipe operation.
