---
name: botte-proxy
description: "Transparent LLM compression proxy for botte-secrete — sit between any AI agent and its LLM API to compress requests by 40-95%. Use when you want token savings without changing agent code."
---
# Botte Proxy

Transparent HTTP proxy that compresses LLM API requests before forwarding them. Inspired by Headroom's proxy mode.

## Features

- **Transparent** — sits between any OpenAI-compatible agent and its LLM API
- **Universal compression** — uses Universal Compressor's smart routing (JSON, code, logs, tool output)
- **Reversible** — originals are cached for retrieval on demand (CCR-like)
- **Dashboard** — real-time savings dashboard at `http://localhost:PORT/dashboard`
- **Stats API** — JSON stats at `http://localhost:PORT/stats`
- **Local-first** — your data never leaves your machine

## Usage

```bash
# Start proxy (default target: http://localhost:11434/v1 for Ollama/LocalAI)
python -m skills.botte_proxy.cli proxy --port 8787

# With specific target
python -m skills.botte_proxy.cli proxy --target http://192.168.1.47:11434/v1 --port 8787

# With OpenAI
python -m skills.botte_proxy.cli proxy --target https://api.openai.com/v1 --api-key $OPENAI_API_KEY

# View stats
python -m skills.botte_proxy.cli stats

# View dashboard
open http://localhost:8787/dashboard
```

## Agent Integration

Point any OpenAI-compatible agent at the proxy:

```bash
# Claude Code
CLAUDECODE_API_BASE=http://localhost:8787 claude

# Any OpenAI client
export OPENAI_BASE_URL=http://localhost:8787/v1

# Generic
export OPENAI_API_BASE=http://localhost:8787/v1
```

## Architecture

```
Agent → Proxy (port 8787) → Compress messages → Forward → LLM API
         ↓
      Dashboard (/dashboard)
      Stats (/stats)
```
