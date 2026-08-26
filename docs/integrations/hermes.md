# Botte Secrète × Hermes-Agent — integration guide

> Status: reference integration, written from botte-secrète's side. Hermes-
> Agent's exact tool-calling format wasn't verified against their live repo
> at the time of writing — see the caveat at the bottom before wiring this in.

## Why

Hermes-Agent's [[hermes-second-brain]] pattern (Goal Layer → Knowledge Layer →
History Layer → Filter, compounding via Qdrant) filters every response
through three layers before answering — but every one of those layers still
calls a model to reason, even when the task is trivial (rename a variable,
classify a diff, extract a field). Botte-secrète's belt intercepts exactly
that trivial tier before it reaches a paid model:

```
Hermes task → [botte: micro-NN → deterministic → local LLM → cloud]  → Hermes continues
                 0 tok      0 tok         0 cloud tok      only if truly needed
```

Every task the belt resolves locally or deterministically is one Hermes
never has to spend cloud tokens on. This isn't a replacement for the
second-brain pattern — it's a cost filter that sits in front of it.

## Two integration paths

### Path A — Hermes speaks MCP (zero code)

If Hermes-Agent's tool layer can register an MCP server, this is the entire
integration:

```bash
python -m skills.hermes_bridge.cli config --cwd /path/to/botte-secrete
```

Paste the printed block into Hermes' MCP client config. Botte's
`skills.llm_mcp.server` then exposes its full tool surface (auto_route,
local_chat, fusion, find_skills, infra_tips, and ~30 more) the same way it
does for Claude Code or Cursor today.

### Path B — Hermes expects function-calling tool specs (no MCP)

If Hermes' tool registry instead expects a flat list of OpenAI-function-
calling specs + a dispatcher — the more common shape for agents built before
MCP existed — use [[hermes_bridge]]:

```python
from skills.hermes_bridge import TOOL_SCHEMAS, dispatch

# 1. register TOOL_SCHEMAS with Hermes' tool-calling mechanism
# 2. when Hermes calls one of them, forward to:
result = dispatch(tool_name, tool_args)   # returns a JSON string
```

`TOOL_SCHEMAS` covers the focused tools that matter for a routing/second-brain
integration: `botte_auto_route`, `botte_local_chat`, `botte_fusion`,
`botte_find_skills`, `botte_infra_tips`, and `botte_qa_agent_run`. The final
tool accepts a strict `botte.agent-run/v1` manifest and emits the same private,
idempotent outcome contract used by Codex through MCP. See [[hermes_bridge]]
for the full schema and per-tool description.

An agent return is only a partial fact. Do not send raw answers, stdout, stderr,
or local paths in a manifest; unsupported fields are rejected. A `PASS` becomes
a verified Quality Compass label only when an allowed external verifier and at
least one evidence reference are supplied.

## Where to put the filter in Hermes' pipeline

Recommended: right after the **Goal Filter**, before **Knowledge
Retrieval** — trivial tasks (formatting, renames, simple classification)
rarely need goal/history context at all, so intercepting them there saves
both the model call *and* the vector search that would have preceded it.

```
Input → Goal Filter → [botte_auto_route] → trivial? → answer locally, done
                                          → hard?     → Knowledge Retrieval → History Check → Response (as today)
```

## The numbers, checkably

Don't take "it saves tokens" on faith — run:

```bash
python -m skills.bench.cli
```

This runs a fixed, versioned task corpus through the real routing decision
logic (0 tokens spent measuring) and reports the actual token/cost delta
against a "no routing" baseline. See [[bench]] for the methodology and its
stated caveat (short synthetic prompts read local-heavier than real
production prompts with full context).

## Caveat

This guide describes the integration from botte-secrète's side — what it
exposes and how. It was **not** validated against Hermes-Agent's actual
tool-calling implementation (no access to that repo at write time). Before
wiring this in for real:

1. Confirm which path (A or B) matches Hermes' actual tool-registration API.
2. If Path B, confirm the exact function-calling schema Hermes expects
   (OpenAI-style is assumed here as the common denominator — verify).
3. Run [[hermes_bridge]]'s `python -m skills.hermes_bridge.cli call <tool>
   --prompt "..."` locally first to confirm the dispatcher behaves as
   expected before trusting it inside a live Hermes session.
