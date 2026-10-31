# Parcimonia task assessment — candidate validation

Date: 2026-10-30. Base: `87c45aaaa46e8e0d17db7db6aec1a179b1938af7`.
Candidate: Botte Secrète 1.11.0, advisory helpers only.

- `python -m unittest skills.preflight.test_assessment skills.preflight.test_github_plan skills.llm_mcp.test_assessment_tools skills.plugins.test_distribution -q`: 38 tests pass on final Python sources.
- `python -m skills.llm_mcp.test_lazy`: 33 checks pass, including schema/dispatch agreement and core/on-demand discovery.
- `python -m skills.app_test.test_app_test`: 14 checks pass for existing generation/artifact behavior; no real GUI runner or game was exercised.
- `python scripts/pre-commit-check.py --fast`: staged secret, JSON and syntax checks pass (8 Python files).
- Project checkup completed. It reports no project-local MCP wiring in this cloud checkout; this is not an installed-machine or model-backend qualification.

Independent review found and prompted corrections for typographic negations,
cloud testing-tool variants, Unicode query expansion, base retarget invalidation
and cardinality-aware shortlist selection. The final regressions cover those
cases. Search and plans are intentionally bounded; lexical assessment may
abstain or miss an unsupported phrasing.

A real read used a Parcimonia-generated target for GitHub PR 145, then the
connected GitHub reader observed `merged=true` and
`merged_at=2026-10-13T17:13:16Z`. This tests the read-planning workflow, not its
performance. A separate scoped lexical search for Parcimonia returned zero
matches; that query is not evidence that no related work exists.

No provider-token measurement, end-to-end speed comparison, real-time playtest,
local deployment or public-directory listing was established by these checks.
The Site-hosted JavaScript implementation is a separate deployment with its own
source commit and tests; its lexical scores are not interchangeable with the
Python fuzzy ranking scores.

## Continuation: live cloud use and GitHub compaction

The published `assess_task` and `plan_github_research` tools were called through
the connected Botte Secrète plugin. They prepared the PR 147 inspection, then the
host's GitHub reader fetched current metadata, filenames, exact-head checks and
statuses. The observed head was `004c6f31631800d0e02290f99d9e14606f830867`;
the PR remained open, draft and unmerged at that observation.

The failing GitHub job had passed its runtime tests, then failed README version
validation because the French badge still said 1.10.0. Aligning it to 1.11.0
changed the local documentation check from 10 passed/1 failed/10 skipped to
11 passed/0 failed/10 skipped. No runtime assertion was relaxed.

Final checks for this increment:

- Canonical `python scripts/run_tests.py -q`: **1127 passed, 0 failed, 75 suites**
  after installing declared project dependencies with `python -m pip install -e .`.
  The initial minimal cloud environment had six failures caused by missing
  `typer` and tree-sitter imports; this environment issue was resolved.
- Parcimonia's 48 behavioral/MCP tests are now included in that canonical runner,
  including selection of the suite when its dependency files change.
- Cloud `npm test`: **51 passed, 0 failed**; compiled Worker summary dispatch passes.
- Documentation links: 73 Markdown files, 0 broken local links.
- Offline replay: five authored cases retain their expected proposal/abstention
  outcomes. These are examples rather than task-accuracy or gameplay results.

The separate cloud service is version 0.3.0, deployed as Site version 3 from
source commit `b60d9ec8f537899e5634a848796cb89aef0b3219`.

### Observed JSON size comparison

The recorded input combines real PR metadata, file headers and check/status
responses. File patches were projected out before this comparison. It was then
processed by `summarize_github_evidence` without a model or network call.

| Measurement | Observed value |
| --- | ---: |
| Supplied JSON, UTF-8 | 68604 bytes |
| Compact summary JSON, UTF-8 | 4192 bytes |
| Difference | 64412 bytes, 93.89% |
| Provider tokens / cost / total-task latency | unknown |

The summary retains 9 successful, 2 cancelled, 1 failed and 1 skipped check,
with revision identities, source links and explicit omitted-row counts. It does
not declare the PR passing or eligible to merge. Completeness remains unknown
unless declared by the caller; supplied data remains unverified.

Input SHA-256:
`2977190c91a317d276c6ccacc4419b6cf7ccba073b5a5e81426841de814782e6`.
Compactor source SHA-256:
`5edfd38b3ecc9efb84e26adf311c1a961929e9ba4ee4ab32413f0f9bf05f48b7`.
The input and generated replay report remain outside this public repository.

This comparison excludes input projection, MCP framing, host reasoning and
later detail reads. The cloud result carries both text and structured data,
so its transport envelope is larger than the measured JSON summary. No billed
token reduction or end-to-end acceleration follows from this byte measurement.

Independent review regressions cover truncation indicators, malformed dates,
detail URL handling, bounded categories, revision mismatches and self-sizing
digit boundaries. Integral JSON literals are the portable numeric input form;
Python rejects a float literal such as 1.0 where JavaScript represents it as an
integer. Real GitHub integer fields use the portable form.

## Selective first-assessment continuation

The connected cloud tools were used for first assessment, PR planning and the
GitHub evidence summary. A live witness exposed an unnecessary abstention:
`Retrouver les PR liées à une régression de reconnexion` was interpreted as both
GitHub research and test execution. The correction distinguishes the subject of
an explicit GitHub search from an additional command. Separate commands still
abstain. The grammar remains deliberately bounded rather than a general parser.

The existing local hook now calls the assessor itself, reuses that first pass
for bounded guidance and emits nothing for trivial or unsupported input. It
does not call a model or execute tools. Its assessor import is inside the
fail-open boundary: a missing module produces no context and exit 0. The hook
is the existing Claude Code integration; the Codex plugin and Work cloud do not
run it. Their broader skill metadata and workflow instructions guide host
selection without guaranteeing it. Existing customized project policies are
not overwritten by the generated defaults.

Final source checks for this increment:

- Canonical Python runner: **1140 passed, 0 failed across 75 suites**.
- Targeted preflight: 18 tests; bootstrap: 13 checks; assessment: 20 tests.
- Cloud after preserving the parallel statistics update: **262 tests passed**;
  compiled Worker research and statistics dispatch succeeded.
- Documentation: 11 passed, 0 failed, 10 intentionally skipped commands;
  73 Markdown files, 0 broken local links.
- Project checkup completed; the temporary source checkout still reports no
  project-local MCP configuration. No claim about a user's installed machine
  follows from this source validation.

The source history advanced concurrently to
`1ff900bb7a2465d1b3ea90f94f7e559ce52a8d34`, which added statistics. A normal push
rejected the older source base. The current source was reopened and only the
assessment correction was reconciled; the statistics engine, fixtures and tests
remain byte-identical to that parallel commit. The combined service candidate
is 0.5.0 from `336c5a7ea610f8f687a11f32c3077d8c67222dea`.
Site version 5 deployed successfully. The same live research witness changed
from `abstained` with research/testing labels to `proposed/github_research`
after deployment, with the same supplied tool inventory. A separate request
to find PRs and then run tests still abstains. The statistics intent remains
available; no tool execution is inferred from that assessment.

### Hook context comparison

These five authored probes compare the previous hook at `dadbbe83d4aa07950dfbcb569a0cb2763aaa987a`
with the candidate using the same current skill catalog. Sizes cover the returned
context string only, excluding CLI framing and the host's task completion.

| Prompt | Previous UTF-8 bytes | Candidate UTF-8 bytes |
| --- | ---: | ---: |
| bonjour | 216 | 0 |
| merci | 264 | 0 |
| continue | 216 | 0 |
| Retrouver les PR liées à une régression de reconnexion | 289 | 364 |
| Find GitHub PRs then run tests | 285 | 171 |

The research hint is longer because it carries the scoped workflow and checks.
The trivial prompts receive no hook context. These examples establish selective
emission, not general accuracy, billed-token reduction or end-to-end speed.
