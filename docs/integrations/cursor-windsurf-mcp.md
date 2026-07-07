# MCP Integration — Cursor / Windsurf

Botte Secrète's MCP server (`skills/llm_mcp/server.py`) exposes 20+ tools
that can be used from any MCP-compatible agent.

## Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "botte-secrete": {
      "command": "python3",
      "args": ["-m", "skills.llm_mcp.server"],
      "cwd": "/path/to/botte-secrete"
    }
  }
}
```

## Windsurf

Add to `.windsurf/mcp.json` (same format as Cursor).

## Available tools

| Tool | Description |
|------|-------------|
| `route_task` | Recommend cheapest model tier for a task |
| `local_chat` | Run prompt on local model (0 cloud tokens) |
| `bench_run` | Run benchmark, return savings metrics |
| `doctor` | Full project health checkup |
| `fleet_status` | Aggregate status across all projects |
| `context_profiler` | Measure always-on token prefix |
| `discover_backends` | Scan for local LLM servers |
| `audit_local_usage` | Hardware profile + setup steps |
| `find_skills` | Search skill catalog by keyword |
| `nlp_extract` | Deterministic entity extraction |
| `schedule_plan` | DAG topological sort for task ordering |
| `assign_work` | Load-balance tasks across workers |

See `skills/llm_mcp/SKILL.md` for the complete list.
