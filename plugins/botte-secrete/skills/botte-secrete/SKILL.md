---
name: botte-secrete
description: Use the separately installed Botte Secrète local runtime for context budgets, compression, routing, code audit and evidence workflows. Use when the user asks to use Botte Secrète through its local MCP tools. Not for installing unknown packages, providing model weights or treating this plugin as the runtime implementation.
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

For work requiring tool selection or research planning, call `assess_task` when
available. Pass the user's task and a small inventory of relevant tools actually
available in the current session. Read the shortlisted tool's real schema before
calling it. Metadata and lexical scores do not verify capabilities or authorize
execution. An abstention returns interpretation to the host agent. Skip this
extra round trip when a trivial task already has an obvious direct action.

For scoped GitHub/PR research, use `plan_github_research` then an available GitHub
reader. Retain source links, pagination limits and observed revisions; closed
is not merged. Revalidate both head and base before reusing diff evidence.

For software tests or game playtests, use the proposed checks with the existing
test workflow. Verify capture, input, assertions, stop conditions and target
build separately. A plan or test generator does not prove a running test or
real-time gameplay. Report actual results and unknown measurements separately.
