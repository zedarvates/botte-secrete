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
