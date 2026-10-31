# Botte Secrète — project policy (read every turn)

Shared rules for all agents and developers on this project. Keep cheap, keep local.

## Parcimonia before substantive work
- Before a substantive task or a materially different phase, call `assess_task`
  if exposed by the connected Botte Secrete runtime. Supply the task and a small
  inventory of relevant tools actually available; inspect their real schemas.
- Reuse the assessment for a homogeneous batch. Reassess when the goal,
  constraints, available tools or failure evidence changes; skip trivial direct
  actions. Do not add an assessment before every file read or command.
- Before scoped GitHub/PR research, use `plan_github_research` when available,
  then execute the reads with a real GitHub tool. Keep revisions and read limits.
- If a helper is absent, fails or abstains, note the limitation once and let the
  host choose a suitable available workflow. Preserve the user's language,
  negations, constraints and permissions; do not retry merely to force a route.
- These helpers provide advisory plans, not execution or authorization. Verify
  actual results and count assessment overhead before claiming any savings.

## Routing (cost)
- Use Parcimonia for the first assessment of work that needs research, tool
  selection, code changes or test planning, when `assess_task` is available.
  Reuse a current preflight assessment; skip extra calls for trivial requests
  and direct actions whose tool and scope are already clear.
- Treat lexical proposals as hints. Check the actual offered tool schema and
  prerequisites; an abstention returns interpretation to the host. Do not infer
  permission, risk, locality or a working local backend from prompt wording.
- For GitHub/PR research, prepare scoped reads with `plan_github_research`, use
  the connected GitHub reader, then `summarize_github_evidence` for bulky supplied
  results when useful. Retain source links, completeness and head/base revisions.
- Prefer deterministic helpers and verified cache reuse for cheap transformations.
  Use a local model only when its backend and task suitability are established.
  Keep genuine architecture, security and debugging reasoning with the host.
- No model call inside a helper does not imply zero host tokens or free compute.
  Measure the accepted workflow, including tool overhead, retries and fallback.
- Prefer `rtk <command>` when available for compact terminal output.

## Prompts
- For an ambiguous request, use the existing evidence and host judgment to
  clarify or split it. Consider `improve_prompt` only when useful and available.
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
- Keep the host's configured effort. These helpers do not change the model
  or its effort setting; compare actual accepted results before claiming savings.
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
