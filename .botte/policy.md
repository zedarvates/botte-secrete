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
- Prefer concise, clear output. `python -m skills.caveman.cli prompt --level light`
  prints an optional style prompt; it does not inject or activate it.
  Preserve language, negations, conditions, uncertainty and evidence.

## Compression
- **Output**: choose a concise style explicitly; `context_budget` selects context
  and does not automatically inject Caveman prompts. Measure paired model outputs
  before claiming style savings.
- **Input**: Caveman `compress` is read-only size analysis, not file compression.
  Keep instructions and evidence exact. Select relevant context before compacting it.
- **JSON reports**: `universal_compressor` removes whitespace without deleting values.
- **Logs/CI output**: preserve distinct lines, errors and chronology; only exact
  consecutive repetitions may be summarized. Report measured UTF-8 byte reduction
  separately from tokenizer counts and provider usage.

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
- A tight budget can justify shorter presentation, but cannot remove evidence,
  permissions or necessary reasoning. No budget-triggered Caveman activation is
  implemented by these standalone commands.
