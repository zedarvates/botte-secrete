# Botte Secrète — project policy (read every turn)

Shared rules for all agents and developers on this project. Keep cheap, keep local.

## Routing (cost)
- **Default to LOCAL** for cheap/transformational work: classification,
  extraction, short summaries, translation, formatting, syntax checks, and
  **choosing which skills/tools to use**. Use the `botte-llm` MCP tools
  (`local_chat`, `auto_route`, `find_skills`) — these cost 0 cloud tokens.
- Escalate to the cloud model **only** for genuine reasoning: architecture,
  multi-file changes, security, debugging root-causes.
- Prefer `rtk <command>` for terminal commands (compact output).

## Prompts
- Before a big/ambiguous request, improve it locally (`improve_prompt`) so the
  cloud model starts from a structured, unambiguous prompt.

## Hygiene (drift)
- After a component update or before a checkup, run `/checkup` (or
  `python -m skills.checkup.cli .`) — directives + metrics + infra + drift.
- Keep `CLAUDE.md`/`AGENTS.md` under ~2000 tokens and free of stale path refs.

## Budget
- Daily token budget: 50000 (auto_router downgrades when exceeded).
