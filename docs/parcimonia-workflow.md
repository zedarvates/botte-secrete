# Parcimonia task assessment and research

Candidate version: Botte Secrète 1.11.0. The corresponding cloud helpers run
without a local Python runtime. Both produce advice from supplied data, with
no model call, network access, execution or persistent storage in the helpers.
The host still interprets the task, reads real tool schemas and verifies results.

## First assessment

Call `assess_task` with the task and a small inventory of tools actually available
to the current host. This is useful before research, code work, transformations,
software testing or game playtests. Skip extra calls for obvious trivial work.

```json
{
  "task": "Rechercher les PR GitHub ouvertes",
  "available_tools": [
    {"name": "github_search_prs", "description": "Search GitHub pull requests"}
  ],
  "context_budget": 2000
}
```

The result names a supported intent, proposes up to five offered tools and lists
steps, checks and missing prerequisites. A tool name is a discovery hint, not a
validated call. Unsupported, negated or ambiguous requests abstain. This is a
conservative lexical heuristic, not a general language or authorization parser.
Risk, permission, locality and real-time capability remain unknown.

Inputs: task at most 16 KiB UTF-8, at most 64 tool records, each description at
most 2 KiB, budget 0–16000 estimated metadata tokens. The estimate uses character
count divided by four; it is not billed usage. Cloud uses exact lexical ranking;
Python reuses the existing fuzzy skill finder. Scores must not be compared
between implementations or interpreted as calibrated confidence.

## GitHub and pull requests

Call `plan_github_research` with an explicit `owner/repo`, optional query and
optional `pr_number`. Execute relevant reads through a separately available
GitHub connector. The helper cannot search GitHub itself or use credentials.

```python
from skills.preflight.github_plan import plan_github_research
plan = plan_github_research("zedarvates/botte-secrete", pr_number=145)
```

The plan starts with current metadata and progressive reads. Keep filenames,
patches and checks tied to observed revisions. Revalidate the head and base
before relying on diff evidence. Closed, draft, merged, checks pending and checks
missing are different states. Record pagination, incomplete searches, failed
reads and missing patches; a partial read cannot establish absence.

Free text is converted to quoted lexical terms inside the explicit repository
scope. This intentionally limits search syntax; it is not a replacement for all
GitHub search operators. A zero-result search may require a different lexical
query or direct reference. No result is cached or promoted into verified memory.

## Exact file duplicate inspection

The Python runtime can inspect an explicit local directory through
`find_file_duplicates`. Parcimonia assessment can shortlist that tool for
explicit file-duplicate searches. Size/hash groups require byte comparison;
hard links, partial scans and omitted results stay distinct. See the
[file-duplicate contract](file-duplicates.md). This does not change the hosted
cloud tools or add desktop behavior.

## Deterministic statistics

For an explicit request to compute descriptive statistics, `assess_task` can
propose the `statistics` intent and shortlist an available `compute_statistics`
tool. The Python runtime computes supplied values through that separate tool;
assessment itself remains advisory. See the [statistics contract](statistics.md)
for operations, input limits, missing-data policy and percentile conventions.
This Python increment does not update the independently hosted cloud helpers.

## Software and game tests

`assess_task` can prepare these workflows; it does not run a test. Existing
`skills/app_test/generator.py` can generate visual test scripts and invoke an
installed SikuliX/OculiX runner. Its available actions include waiting, clicking,
typing and visible/absent assertions. A runner, display, target application and
reference images are separate prerequisites. The unit tests of the generator
do not establish end-to-end GUI success on a user's machine.

For a game pilot, qualify a menu or deterministic scenario first. Continuous
gameplay needs an adapter that supplies timestamped observations, bounded inputs
and independent assertions. Reuse Parcimonia's `DecisionBudget` and
`assess_decision_timing` to detect missed deadlines and stale observations;
those contracts do not provide capture, input or a clock by themselves.

Record the build/commit, scenario/seed, adapter and verifier versions, allowed
actions, stop condition and action/duration budgets. Retain transitions,
failures and capture references. Measure success, total time to verified outcome,
capture-to-action latency p50/p95, missed deadlines, stale actions and resources.
No real-time game performance has been established by this increment.

## Distribution and measurement

The Codex Git marketplace package needs its separately installed compatible
Python runtime. The Site-hosted cloud tools process supplied inputs in memory
and do not connect to the user's local machine. Updating either deployment does
not update the other. No hooks are required for these helpers.

A public Git repository or publicly reachable Site is separate from acceptance
in the public plugin directory. Verify installation, authentication, listing
approval and publication before filming instructions to search and install.
See the [English video draft](demos/parcimonia-introduction.md).

For a paired comparison, keep task, target revision, success criteria and tool
availability equal. Measure the whole accepted task, including assessment calls,
results, retries and fallback. Record provider usage only when actually exposed;
otherwise retain `null`. Byte reductions and metadata estimates do not prove
token, price or latency savings. Keep failures and abstentions in the results.
