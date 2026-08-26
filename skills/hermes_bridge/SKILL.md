---
name: hermes-bridge
description: Expose routing, local chat, fusion, skill search, infrastructure advice, and privacy-safe QA run manifests to Hermes-Agent or another OpenAI-function-calling framework, plus a one-call MCP config generator. Use when connecting botte-secrète's routing and evidence contracts to another agent framework.
---

# hermes_bridge — connect the belt to another agent framework

botte-secrète already runs a standard MCP server (`skills.llm_mcp.server`,
stdio JSON-RPC). If the target framework speaks MCP, **that's the whole
integration** — no code in this module runs:

```bash
python -m skills.hermes_bridge.cli config --cwd /path/to/botte-secrete
# → paste the printed {"mcpServers": {...}} block into the framework's MCP config
```

This module exists for frameworks — [[hermes-second-brain]] among them — that
instead expect a flat list of OpenAI-function-calling tool specs + a
dispatcher, a common shape for agents built before/without MCP support.

```bash
python -m skills.hermes_bridge.cli schemas          # focused tool specs, OpenAI-shaped
python -m skills.hermes_bridge.cli call botte_auto_route --prompt "rename x to y"
```

```python
from skills.hermes_bridge import TOOL_SCHEMAS, dispatch

# register TOOL_SCHEMAS with the framework's tool-calling mechanism, then:
dispatch("botte_auto_route", {"prompt": "..."})   # → JSON string, same shape as the MCP tool
```

## Focused tools

Deliberately a subset of the ~35-tool MCP surface — the ones that matter for
a second-brain / routing integration:

| tool | what it does |
|------|----------------|
| `botte_auto_route` | decide local-vs-cloud (0 tokens); `execute=true` to actually run it |
| `botte_local_chat` | run a prompt on a local model — 0 cloud tokens |
| `botte_fusion` | cascade / draft_refine / vote — models collaborating |
| `botte_find_skills` | 0-token local search over installed skill catalogs |
| `botte_infra_tips` | hardware/software setup advice for running local models |
| `botte_qa_agent_run` | emit a strict private run outcome without trusting agent self-report |

## Why this matters for a second-brain agent

Every task [[hermes-second-brain]] would otherwise send straight to its own
model gets a chance to resolve locally or via the cheapest capable tier
first — see [[bench]] for the measured (not asserted) savings from that.
`botte_find_skills` also gives Hermes 0-token access to the local skill
catalog instead of re-deriving capabilities from scratch each session.

Related: [[llm_mcp]] (the native MCP server this bridges from), [[auto_router]],
[[bench]] (the proof), `docs/integrations/hermes.md` (the full integration write-up).
