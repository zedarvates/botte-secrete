---
name: botte-secrete
description: Use connected Botte Secrète and Parcimonia for first assessment of research, GitHub/PR review, tool selection, code changes and software or game test planning, and for deterministic statistics, exact file duplicates or local Markdown links. Use without requiring a Botte mention; skip trivial conversation and obvious direct actions. Requires a separately installed compatible runtime.
license: MIT
metadata:
  version: "1.11.0"
---

# Botte Secrète local workflow

1. Confirm that the compatible Botte Secrète runtime is already installed and that
   `botte-mcp` is available to Codex. The plugin bundles instructions and MCP
   wiring, not Python implementations or optional dependencies. For a missing
   runtime, use the plugin README when installation is requested; otherwise
   continue the task with suitable available host tools.
2. Inspect the connected `botte-llm` server's tools and real schemas. Select a tool
   supported by that installed version; do not invent names, arguments, service
   endpoints or CLI subcommands. Verify any required local backend or adapter.
3. Preserve the user's task scope and host permissions. Availability does not
   authorize publishing, sending messages, changing credentials or starting
   unrequested external jobs.
4. Report actual results, relevant evidence and remaining prerequisites. Keep
   measured results separate from estimates; no token, price or speed saving is
   established by a helper merely avoiding a model call.

## Parcimonia first assessment

Before substantive work or a materially different phase, reuse a current
Parcimonia assessment from the local preflight when one is supplied. Otherwise
call `assess_task` when available. Supply the task and a small inventory of
relevant tools actually available in the current session. Inspect shortlisted
schemas and prerequisites: metadata and lexical scores do not verify capability
or authorize execution.

Reuse the assessment for a homogeneous batch; reassess when the goal,
constraints, available tools or failure evidence changes. Skip this extra round
trip for trivial work and obvious direct actions.

If a helper is absent, fails or abstains, note the limitation once and let the
host choose a suitable available workflow. Preserve the user's language,
negations, constraints and permissions. Do not repeat calls merely to force a
route, install a runtime or start a model automatically. Include assessment
overhead in any measured comparison of total task cost.

For scoped GitHub/PR research, use `plan_github_research` then an available GitHub
reader. Retain source links, pagination limits and observed revisions; closed
is not merged. Revalidate head and base before reusing diff evidence. For bulky
supplied metadata, use `summarize_github_evidence` when available, retain original
read references and inspect omitted details. Its completeness is caller-declared
and its size measure covers compact JSON bytes, not tokens or the entire MCP call.

For numeric data, use `compute_statistics` with explicit missing-value and
percentile conventions. For exact file copies, `find_file_duplicates` requires
an explicit local root and distinguishes hard links and partial scans; it does
not judge similar images or removable content. `check_local_links` compares
supplied Markdown and repository paths; an incomplete inventory cannot prove
that an absent target is missing. Verify current schemas before these calls.

For software or game tests, use the proposed checks with the existing test
workflow. Qualify capture, input, assertions, stop conditions and target build
separately. A plan or generator does not prove execution or real-time gameplay.
The local preflight hook integrates with Claude Code; this plugin supplies no
Codex or Work-cloud lifecycle hook and cannot force the host to select a skill.
