---
name: botte-secrete
description: Use the connected Botte Secrète runtime and Parcimonia helpers for first assessment of research, GitHub/PR review, tool selection, code changes and software or game test planning. Use for these tasks without requiring the user to name Botte. Skip trivial conversation and obvious direct actions; verify current schemas and prerequisites. Local runtime installation is separate from this plugin.
license: MIT
metadata:
  version: "1.11.0"
---

# Botte Secrète local workflow

1. Confirm that the compatible Botte Secrète runtime is already installed and that
   `botte-mcp` is available to Codex. The plugin bundles instructions and MCP
   wiring, not Python implementations or optional dependencies. If the server
   cannot start, report the missing prerequisite and use the plugin README's
   runtime setup instructions for an installation request. For an ordinary task,
   continue with available host tools; do not block the work or install a runtime
   merely because an optional helper is missing.
2. Inspect the connected `botte-llm` server's available tools and their schemas.
   Choose a tool supported by that installed version; do not invent tool names,
   arguments, service endpoints or CLI subcommands.
3. Check the chosen workflow's prerequisites. Local model providers, external
   tools and optional Python packages may be needed. Report unavailable components
   before executing a workflow that depends on them.
4. Use deterministic checks, context budgets and routing evidence where the
   runtime exposes them. Distinguish measured results from estimates; do not
   promise token savings, benchmark scores or a successful audit without evidence
   from the actual run.
5. Keep the user's task scope and host permission rules. Runtime tool availability
   does not authorize publishing, sending messages, changing credentials or
   starting unrequested external jobs.
6. Explain the result, relevant evidence and remaining prerequisites. Preserve
   the project's licence and third-party provenance boundaries when using
   upstream integrations or redistributing artifacts.

## Parcimonia first assessment

For work requiring tool selection or research planning, reuse a current
Parcimonia assessment from the local preflight when one is supplied. Otherwise
call `assess_task` when available. Pass the user's task and a small inventory of relevant tools actually
available in the current session. Read the shortlisted tool's real schema before
calling it. Metadata and lexical scores do not verify capabilities or authorize
execution. An abstention returns interpretation to the host agent. Skip this
extra round trip when a trivial task already has an obvious direct action.

For scoped GitHub/PR research, use `plan_github_research` then an available GitHub
reader. Retain source links, pagination limits and observed revisions; closed
is not merged. Revalidate both head and base before reusing diff evidence.
For bulky supplied PR metadata, file headers and checks, use
`summarize_github_evidence` when available. Keep the original read references and
inspect omitted details as needed. Its completeness is caller-declared and its
size measurements cover compact JSON bytes, not tokens or the entire MCP call.

For software tests or game playtests, use the proposed checks with the existing
test workflow. Verify capture, input, assertions, stop conditions and target
build separately. A plan or test generator does not prove a running test or
real-time gameplay. Report actual results and unknown measurements separately.

For a compatible local candidate exposing `botte verify --help`, reuse its
bounded verification workbench: reduce a reproduction with the same failure
fingerprint, triage repeated observations, compare supplied cloud/local sources,
challenge Python tests with mutations, or explore explicit allowed interface
actions. The canonical runner also supports opt-in observed test ordering with
`--prioritize`, retaining every selected suite. Inspect each installed command's
help and prerequisites first. Command execution requires explicit trusted local
adapters and the user's task scope; these capabilities are not cloud execution
endpoints. Preserve process/source identities, inconclusive states, all observed
failures and known comparison differences. A model replay or HTTP navigation
adapter does not establish graphical or real-time game control.
