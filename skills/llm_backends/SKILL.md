---
name: llm_backends
description: Discover, audit and use local LLM servers, or configure portable task-specific inference profiles for a user's machines and existing memory. Use for local models, LM Studio, Ollama, hardware-aware setup, local inference benchmarks or native speculative profiles. Not for training draft models or treating two chat APIs as speculative decoding.
---

# llm_backends — Local LLM discovery, audit & routing

Turn idle local hardware into a token-saving tier. Every task served by a local
model is a task **not** billed to the cloud.

## When to use

- The user mentions **LM Studio, Ollama, LocalAI, vLLM, llama.cpp**, "local model",
  "run it locally", or "use my GPU".
- You need to know **what models are reachable** (this machine or the network).
- A task is cheap/local-suitable (classification, extraction, short summary,
  routing, spell-check, simple Q&A) and could skip the cloud entirely.
- The user has **no** local model yet and wants step-by-step, hardware-aware setup.
- A user wants their own LLM to adapt Botte to different hosts, GPU layouts or memory systems.

## Portable runtime and memory setup

Read [the bundled runtime guide](runtime-guide.md) for this workflow.
Use `botte runtime inspect`, `schema`, `template`, `validate` and `plan` to build
a private `.botte/runtime.json` from the user's observed system. The matching
MCP tools are `runtime_template` and `runtime_plan`; both are offline/read-only.
Do not copy a maintainer's hostnames, keys, model names or memory locations.

Keep a direct baseline. Describe speculative local/remote profiles only when
the installed native engine supports the pinned target/draft combination.
Placement and compatibility references remain declarations, not attestation or
GPU reservations. `ready` marks a complete config, not proof of speed or
speculation. Existing user authorization governs any execution.

Reuse memory with `none`, `botte_http`, or a versioned external context packet
and observation outbox. The external adapter selects authorized entries; Botte
does not migrate a store or import unreviewed memory as instructions. Keep
fallback profiles inside the explicit memory destination list.

`run` and `benchmark` perform real bounded HTTP inference and write private run
artifacts; they never execute model-produced tools or code. Benchmark frozen
tasks/context against distinct preconfigured endpoints; inspect failed checks
and real outputs before proposing task routes. Syntax checks are not semantic
quality evidence. Reports never automatically promote a profile or memory.

With `botte_http`, `--record-memory` or `capture` writes a private quarantined
observation. After a lost receipt, retry only `capture` with the exact outbox
and original identity credential. Never repeat inference as a memory retry.
An interrupted run directory is not resumable; inspect its saved state.
Use existing authorization and ask only for genuinely missing access or facts.

## Quick commands

```bash
# Discover + register backends (writes configs/llm-endpoints.json)
python -m skills.llm_backends.cli scan                 # localhost only
python -m skills.llm_backends.cli scan --subnet        # sweep local /24
python -m skills.llm_backends.cli scan 192.168.1.47    # specific host(s)

# What's registered?
python -m skills.llm_backends.cli list

# Audit: are local models used? what can this machine run? next steps?
python -m skills.llm_backends.cli audit --fresh

# Run a prompt locally (0 cloud tokens)
python -m skills.llm_backends.cli chat "classify: bug or feature?" --max-tokens 128

# Suggest a local model for a project (adaptive per project type)
python -m skills.llm_backends.cli profile ~/my-project
```

## Programmatic use

```python
from skills.llm_backends import registry, quick_chat, audit

registry.refresh()                       # discover + persist
best = registry.best_chat_backend()      # lowest-latency chat backend
model = registry.preferred_model(best)   # coder/instruct over voice/reasoning

res = quick_chat("summarize in 1 line: ...", max_tokens=200)
print(res.text, res.total_tokens)        # all local — no cloud cost
```

## Supported backends

| Backend | Default port | API |
|---------|-------------|-----|
| LM Studio | 1234 | OpenAI `/v1` |
| Ollama | 11434 | native `/api/tags` + OpenAI `/v1` |
| LocalAI | 8080 | OpenAI `/v1` |
| vLLM | 8000 | OpenAI `/v1` |
| Jan / KoboldCpp / text-gen-webui | 1337 / 5001 / 5000 | OpenAI `/v1` |
| ComfyUI | 8188 | image gen |
| Qdrant | 6333 | vector search |

## How it saves tokens

1. **Audit** finds reachable local backends and profiles RAM/VRAM/GPU.
2. **Route** sends local-suitable tasks (see `tiered_router` L0/L1) to a local model.
3. **Call** runs them via the OpenAI-compatible client — zero cloud tokens.
4. **Onboard** users with no local model, selecting a model and server that fit
   their task, per-device capacity and measured constraints.

Related: [[llm_mcp]] (MCP tools for agents), `tiered_router` (cost tiers),
`local_router` (task→backend mapping), `response_cache` (skip repeated calls).
