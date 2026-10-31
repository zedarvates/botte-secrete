# Parcimonia task assessment and research

See the [verification workbench](parcimonia-verification-workbench.md) for
reproduction reduction, observed test order, cloud/local conformance, mutation,
interface exploration and intermittent-failure triage. The
[knowledge inventory](parcimonia-knowledge-inventory.md) locates existing wiki,
RAG/DAG, memory and LLM work with source-pinned documentary links.

Candidate version: Botte Secrète 1.11.0. The corresponding cloud helpers run
without a local Python runtime. Both produce advice from supplied data, with
no model call, network access, execution or persistent storage in the helpers.
The host still interprets the task, reads real tool schemas and verifies results.

## First assessment

Call `assess_task` with the task and a small inventory of tools actually available
to the current host. This is useful before research, code work, transformations,
software testing or game playtests. Skip extra calls for obvious trivial work.
Reuse the result for a homogeneous batch; reassess when the goal, constraints,
available tools or failure evidence changes. Do not assess every individual read.
When a helper is absent, fails or abstains, note the limitation once and let the
host select an available workflow while preserving the user's meaning and
permissions. Do not retry merely to force a proposed route.

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

The plugin's skill metadata now covers these work types without requiring a
Botte mention. Project guidance uses the same first-assessment rule. The local
preflight hook performs a selective assessment itself and supplies bounded
guidance; the host should reuse it rather than repeat the classification.
Trivial requests emit no hook context. This hook is integrated with Claude Code,
not Codex or Work cloud; those surfaces use available skills/tools and host
selection. No package can guarantee that a host will choose a skill every turn.

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

After reads, `summarize_github_evidence` accepts a supplied `report_json` string
up to 128 KiB. Its envelope uses `repository`, `pull_request`, optional
`observed_at`, `files`, `check_runs`, `statuses` and `completeness`. PR and file
objects use GitHub REST fields; checks use `{total_count, check_runs}` and commit
statuses use `{sha, state, statuses}`. Completeness keys are `metadata`, `files`,
`checks` and `statuses`, each `unknown`, `partial` or `complete`. These remain
caller declarations. Omit bodies, patches and logs when only metadata is needed.

The summary retains revision identities, conclusion counts and prioritized
attention items within a 12 KiB compact-JSON bound. Missing merge evidence stays
unknown; no overall merge or passing verdict is produced. Omitted rows and
external/unsafe detail URLs are signalled. Data remains unverified. Exact input
and output UTF-8 byte sizes can show reduction or expansion; host tokens, cost
and total-task latency remain unknown. The MCP wrapper is additional data beyond
the measured JSON summary. Use the original read for omitted details.

## Exact file duplicate inspection

The Python runtime can inspect an explicit local directory through
`find_file_duplicates`. Parcimonia assessment can shortlist that tool for
explicit file-duplicate searches. Size/hash groups require byte comparison;
hard links, partial scans and omitted results stay distinct. See the
[file-duplicate contract](file-duplicates.md). This does not change the hosted
cloud tools or add desktop behavior.

## Supplied local Markdown links

`check_local_links` checks documents and a repository path inventory supplied by
the host. It reports source lines, missing versus unresolved targets and partial
coverage. Incomplete inventories cannot establish absence. It performs no file
access or network request; a host can supply Git-tree filenames and documents at
one observed commit. See the [local-link contract](local-links.md). This Python
increment does not update the independent hosted cloud service or desktop plans.

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

Treat the runner's completion evidence separately from script generation.
The CLI returns success only for a completed, coherent passing run. A missing
runner or launch failure is `not_run`; a zero exit without a final result is
`incomplete`. A nonzero exit, failed step or nonzero final error count fails.
The JSON result and HTML report use the same verdict. These checks validate
the reporting contract; they do not supply a GUI runner or display.

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

## Reuse prior verification observations

When an explicit local Memory Hub contains verification receipts, use
[`botte verify recall`](parcimonia-memory-recall.md) to select bounded status and
counter projections with source/version/report-digest citations. Read a closed
or checkpointed project database; the command does not create a store. Detailed
failure signatures, issue prose and raw reports are outside this searchable
projection. Inspect the cited original report when more detail is needed.

Keep missing, incomplete and unavailable reads distinct. Compare versions only
against explicitly supplied current references, and retain the observation's
quarantine label. Recall supplies evidence to review; it does not promote facts,
change normal context or activate a model route.

When a versioned documentary inventory is supplied, `recall --inventory FILE`
also checks the selected receipt references against exact URI/version identities.
It retains missing, unknown, ambiguous and mismatched references, alongside the
inventory's existing dependency review. No lexical candidate becomes a resolved
relation, and an incomplete read cannot become a complete documentary review.

## Distribution and measurement

The Codex Git marketplace package needs its separately installed compatible
Python runtime. The Site-hosted cloud tools process supplied inputs in memory
and do not connect to the user's local machine. Updating either deployment does
not update the other. No hooks are required for these helpers.

### Portable instructions

New users receive instructions through committed and packaged entry points:

| Entry point | Delivered guidance |
| --- | --- |
| Repository `AGENTS.md` | Links the committed `.botte/policy.md` before substantive work |
| `skills.preflight.policy.DEFAULT_POLICY` | Writes the same Parcimonia section into a new project's `.botte/policy.md` |
| Bootstrap `--create-agents-md` | Creates a missing `AGENTS.md`, links an existing `CLAUDE.md` when present, and points to the policy |
| `skills.preflight.hook` | Runs selective local advisory assessment on Claude Code `UserPromptSubmit`; executes no selected tool |
| Codex plugin `skills/botte-secrete/SKILL.md` | Carries self-contained assessment, reuse and fallback instructions inside the installable subset |

The bootstrap retains existing policy and instruction files. Merge new guidance
into older custom policies deliberately; rerunning setup does not overwrite them.
For a new Codex project, run
`python -m skills.bootstrap.cli /path/to/project --create-agents-md`;
creation is opt-in. New Claude hooks use absolute interpreter
and script paths from the configuring installation. Legacy module-based hooks
are retained and need explicit migration if they resolve an older checkout.
Claude hook wiring is not evidence of an active Codex or global hook. Each host
must expose the real tools, load its supported instructions and verify behavior.
Installing the plugin does not install or activate the separate runtime.

Offline delivery checks from a checkout:

```sh
python -m pytest --rootdir=. -q skills/preflight/test_portable_guidance.py
python -m skills.preflight.test_preflight
python -m skills.bootstrap.test_bootstrap
python -m skills.plugins.test_distribution
```

A public Git repository or publicly reachable Site is separate from acceptance
in the public plugin directory. Verify installation, authentication, listing
approval and publication before filming instructions to search and install.
See the [English video draft](demos/parcimonia-introduction.md).
The [offline replay](demos/parcimonia-workflow-run.md) runs the authored examples
and records helper-only timing and size without executing external tools.
See the [runtime readiness validation](validation/parcimonia-readiness-2026-10-30.md)
for the isolated installed-runtime check, diagnostic scope and GUI runner
completion requirements. A generated script alone is not a completed test.

For a paired comparison, keep task, target revision, success criteria and tool
availability equal. Measure the whole accepted task, including assessment calls,
results, retries and fallback. Record provider usage only when actually exposed;
otherwise retain `null`. Byte reductions and metadata estimates do not prove
token, price or latency savings. Keep failures and abstentions in the results.
