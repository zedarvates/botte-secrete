---
name: mcp_gateway
description: MCP Gateway — expose toutes les skills Botte comme outils MCP. Découverte automatique, schémas d'entrée, transport stdio. Compatible Claude Code, Codex, Cursor, et tout client MCP.
tags: [mcp, gateway, tools, integration, stdio]
---

# mcp_gateway — Botte Secrète MCP Gateway

Expose l'ensemble des skills Botte Secrète comme outils MCP (Model Context Protocol).
Un seul point d'entrée pour que n'importe quel agent (Claude Code, Codex, Cursor, etc.)
découvre et utilise toutes les capacités de Botte.

## Concept

```
Client MCP (Claude Code / Codex / Cursor)
    │
    ▼
mcp_gateway (stdio JSON-RPC)
    │
    ├── security_scanner    → scan . --format json
    ├── fast_context        → explore . "find imports"
    ├── meta_harness        → run plan agents
    ├── botte_nn            → predict model input
    ├── solvers             → assign / pack / schedule
    ├── context_budget      → optimal context budget
    ├── nlp_deterministic   → classify / extract
    └── … (auto-discover)
```

## Usage

```bash
# Test en local
python -m skills.mcp_gateway.server

# Avec un client
python -m skills.mcp_gateway.cli call security_scanner '{"root": ".", "fail_on": "critical"}'
python -m skills.mcp_gateway.cli call fast_context '{"root": ".", "query": "find imports"}'
python -m skills.mcp_gateway.cli list
```

## Configuration

Fichier `.botte-cache/mcp_gateway.json` :

```json
{
  "enabled_skills": ["security_scanner", "fast_context", "solvers"],
  "excluded_skills": []
}
```

Si non configuré, toutes les skills disponibles sont exposées.

## Architecture

```
mcp_gateway/
├── server.py     — MCP server stdio (JSON-RPC 2.0)
├── registry.py   — Découverte des skills disponibles
├── dispatcher.py — Dispatch tools/call vers la bonne skill
├── cli.py        — CLI pour test
└── test_mcp_gateway.py
```
