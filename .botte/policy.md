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
- **Hybrid pipeline**: cloud model plans (2-3 lines), **Ornith-1.0-9B local**
  executes the actual work (0 tokens, 0 cost).

## Prompts
- Before a big/ambiguous request, improve it locally (`improve_prompt`) so the
  cloud model starts from a structured, unambiguous prompt.
- **Caveman style** by default. Activate via `/caveman full` (or ultra for
  max savings). Use `python -m skills.caveman.cli prompt --level full` to
  get the system prompt. Switch back with `/caveman off`.

## Compression
- **Output**: Caveman level depends on budget — light when healthy, ultra when
  tight. Auto-set by `context_budget`.
- **Input** (files, context): Run `python -m skills.caveman.cli compress <file>`
  before loading into context. Typical savings: 46% on AGENTS.md/CLAUDE.md.
- **JSON reports**: Always use `ultra_compact` (-30 to -90%).
- **Logs/CI output**: Use `universal_compressor` with `log` strategy (-80 to 98%).

## Reasoning Effort
- Match effort to task complexity, not model capability.
- **Tiers**: low (trivial) → medium (routine) → high (complex) → extra (hard) → max (critical).
- Cost spread on Fable 5: $3.76/task (low) → $22/task (max) = **82% savings**.
- Default to **high** (best quality/cost ratio). Downgrade to medium for
  routine work. Upgrade to max only for architecture/security.
- In Hermes: set via `/reasoning high` or `reasoning_effort: high` in config.

## Hygiene (drift)
- After a component update or before a checkup, run `/checkup` (or
  `python -m skills.checkup.cli .`) — directives + metrics + infra + drift.
- Keep `CLAUDE.md`/`AGENTS.md` under ~2000 tokens and free of stale path refs.

## Budget
- Daily token budget: 50000 (auto_router downgrades when exceeded).
- When budget < 20% remaining: force caveman **ultra** + reasoning **low**.
- When budget < 50%: force caveman **full** + reasoning **medium**.
