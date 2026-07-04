# Botte Secrète → Hermes Agent Integration Guide

> PR-ready proposal for the Hermes Agent upstream repo (github.com/NousResearch/hermes-agent)

## What Botte Secrète offers

Botte Secrète is a **token-optimization platform** (stdlib Python, 0 heavy deps) that reduces cloud
token usage by ~65% on agent workloads. It provides 5 capabilities any Hermes Agent can use:

### 1. Micro-NN Routing (0 tokens, ~5µs)
4 trained feedforward networks (numpy) that classify effort, route local/cloud, detect anomalies,
and classify errors — no cloud tokens, no network latency. Replaces trivial LLM calls.

```
from skills.auto_router.cli import route
result = route("fix CSS layout bug")
# → {tier: "cheap", effort: 0.42, mode: "cloud", confidence: 0.91}
```

### 2. Deterministic NLP + Solvers (0 tokens)
Regex+gazetteer extraction + OR-Tools solvers for scheduling, assignment, routing.
Pure stdlib, no LLM needed.

### 3. Context Profiler
Measures always-on prefix cost (directives, tool schemas, skill catalog, host overhead).
Identifies the biggest token waste. On a typical Hermes session: ~17K tokens always-on,
~13K reducible.

### 4. Local Harness
Structured output, verification, sandbox execution, and KV-cache-friendly prompt structuring
for Ollama/LM Studio. 51 e2e tests, 0 failures.

### 5. Security Scanner
Taint analysis, malicious pattern detection (30+ patterns, 8 categories), CWE knowledge base
with AI-agent-specific patterns (prompt injection, exfiltration).

## Integration Points

### A. As a Skill (simplest)
Install as a Hermes skill, use from any session:
```bash
# The skill auto-discovers all tools
hermes skills install https://raw.githubusercontent.com/zedarvates/botte-secrete/main/skills/mcp_gateway/SKILL.md
```

### B. As an MCP Server (most powerful)
Run as a standalone MCP server exposing 20+ tools:
```bash
python -m skills.mcp_gateway.server
# → JSON-RPC 2.0 over stdio, auto-discovers all skills via SKILL.md
```

Add to Hermes config:
```bash
hermes mcp add botte --command "python -m skills.mcp_gateway.server"
```

### C. Direct API (for custom integrations)
```python
from skills.auto_router.cli import route
from skills.checkup.cli import run_checkup
from skills.local_harness.executor import run_harness
```

## Measured Token Savings

| Optimization | Before | After | Savings |
|---|---|---|---|
| Always-on context | 16,973 tok | 4,042 tok | -76% |
| Micro-NN routing (eligible tasks) | 100% cloud | 35% cloud | -65% |
| Host skill catalog (286 skills) | 5,720 tok | 0 tok | -100% |
| Lazy tools + on-demand skills | 8,853 tok | 1,200 tok | -86% |

## Concrete Example: Adding `route_task` to Hermes

In `hermes-agent/tools/botte_router.py`:
```python
import json
from tools.registry import registry

def check_requirements() -> bool:
    try:
        from skills.auto_router.cli import route
        return True
    except ImportError:
        return False

def route_task(task: str) -> str:
    from skills.auto_router.cli import route
    result = route(task)
    return json.dumps(result)

registry.register(
    name="route_task",
    toolset="botte",
    schema={
        "name": "route_task",
        "description": "Route a task to the best tier (local/cheap/standard). "
                       "0 tokens, ~5µs via micro-NN. Returns {tier, effort, mode, confidence}.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task description to route"}
            },
            "required": ["task"]
        }
    },
    handler=lambda args, **kw: route_task(task=args.get("task", "")),
    check_fn=check_requirements,
    requires_env=[],
)
```

## Current Status (2026-07-04)

- **51 e2e tests**, 0 failures
- **50+ skills**, 4 micro-NN trained + distilled
- **MCP gateway** with 20+ tools (auto-discovery via SKILL.md)
- **Control loop** with ledger, analyze, adapt (50 synthetic sessions)
- **Demo pipeline**: asciinema → GIF ready
- **hermes_bridge**: response size limiter + MCP compatibility verified

## Next Steps (for human review)

1. [ ] Review the MCP gateway tool schemas against Hermes tool conventions
2. [ ] Decide: skill install vs MCP server vs both
3. [ ] Post this proposal as a GitHub Discussion on the Hermes Agent repo
4. [ ] Consider upstreaming the `route_task` tool as a built-in Hermes toolset
