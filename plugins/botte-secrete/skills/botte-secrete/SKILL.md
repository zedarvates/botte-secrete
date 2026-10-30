---
name: botte-secrete
description: Use before substantive tool selection, GitHub research, code changes, software tests or game playtests when Botte Secrète tools are connected, and when the user requests its routing, compression or evidence workflows. Consult Parcimonia once per phase with reuse and fallback. Requires a separately installed runtime; the plugin does not provide model weights or the runtime implementation.
license: MIT
metadata:
  version: "1.11.0"
---

# Botte Secrète local workflow

1. Confirm that the compatible Botte Secrète runtime is already installed and that
   `botte-mcp` is available to Codex. The plugin bundles instructions and MCP
   wiring, not Python implementations or optional dependencies. If the server
   cannot start, report the missing prerequisite and use the plugin README's
   runtime setup instructions.
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

Before substantive work or a materially different phase, call `assess_task` when
available. Pass the user's task and a small inventory of relevant tools actually
available in the current session. Read the shortlisted tool's real schema before
calling it. Metadata and lexical scores do not verify capabilities or authorize
execution. Reuse the assessment for a homogeneous batch; reassess when the goal,
constraints, available tools or failure evidence changes. Skip this extra round
trip when a trivial task already has an obvious direct action.

If either helper is absent, fails or abstains, note the limitation once and let
the host choose a suitable available workflow. Preserve the user's language,
negations, constraints and permissions. Do not repeat calls merely to force a
route, install a runtime or start a model automatically. Include assessment
overhead in any measured comparison of total task cost.

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
