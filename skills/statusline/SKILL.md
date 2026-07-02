---
name: statusline
layer: GOVERN
description: One-line summary of the belt's session activity (tokens saved, cache hits, local/cloud split, escalations) for a terminal statusline — Claude Code's statusLine hook, tmux, or any shell prompt. Reads .botte/events.jsonl. Use when the user wants a persistent, passive view of savings while they work, or asks to set up a statusline.
---

# statusline — the savings, always visible

```bash
python -m skills.statusline.cli .          # one line, safe to embed anywhere
```

```
🧦 12,480 tok saved · 41 cache hits · 17L/3C · 2 escalated
```

Reads the same `.botte/events.jsonl` as [[demo]] and [[dashboard]] — passive,
0 tokens, no state of its own. `render()` never raises: empty project → `🧦
botte · no activity yet`, missing/unreadable `.botte` → `🧦 botte`.

## Wiring it into Claude Code's statusline

This module does **not** modify your Claude Code settings — wire it in
yourself (or ask an agent to, via the `update-config` skill) by adding to
`.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python -m skills.statusline.cli"
  }
}
```

The CLI also accepts a JSON payload on stdin (Claude Code's statusline hook
convention) and best-effort reads `cwd`/`workspace`/`project_dir` from it, so
it works whether invoked with an explicit path or piped session context.

## Design

- **Best-effort, never blocks the prompt** — any failure (missing file,
  malformed JSON, no `.botte` dir) falls back to a plain `🧦 botte` rather
  than raising or hanging.
- **0 network, 0 tokens** — pure local file read, same guarantee as [[events]].

Related: [[events]] (the data source), [[demo]], [[dashboard]] (the richer views).
