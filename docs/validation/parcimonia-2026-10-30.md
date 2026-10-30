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
