---
name: llm_mcp
description: MCP server that lets Claude Code (or any MCP client) discover and call local LLM servers (LM Studio, Ollama, …) as tools, to offload cheap tasks off the cloud. Use when the user wants to wire local models into their agent, register an MCP server, or have the agent automatically route simple tasks to local hardware.
---

# llm_mcp — Local LLM tools over Model Context Protocol

Exposes [[llm_backends]] as MCP tools so an agent can route work to local models
on its own. Pure stdlib, stdio JSON-RPC 2.0, no dependencies.

## Tools exposed

| Tool | Purpose |
|------|---------|
| `discover_backends` | Scan localhost/network, register reachable LLM servers |
| `list_models` | List models the registered backends expose |
| `audit_local_usage` | Local-usage report + hardware-aware setup steps |
| `route_task` | Recommend cheapest tier + a concrete local backend/model |
| `local_chat` | Run a prompt on a local model (0 cloud tokens) |

## Register in Claude Code

Add to `.mcp.json` at the project root (an example ships at
`configs/mcp.example.json`):

```json
{
  "mcpServers": {
    "botte-llm": {
      "command": "python",
      "args": ["-m", "skills.llm_mcp.server"],
      "cwd": "/absolute/path/to/botte-secrete"
    }
  }
}
```

Then in a session: *"discover my local backends"*, *"classify these 50 tickets
locally"*, *"is local routing active?"* — the agent calls the tools directly.

## Manual smoke test

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"local_chat","arguments":{"prompt":"ping","max_tokens":16}}}' \
 | python -m skills.llm_mcp.server
```

## Token strategy

Tell the agent: *route classification / extraction / short summaries through
`local_chat`, keep architecture & security reasoning on the cloud.* That single
rule typically moves 30-50% of calls to zero-cost local inference.
