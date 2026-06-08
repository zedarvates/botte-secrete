# Hermes Second Brain — Karpathy Pattern

> A self-learning system that filters every AI output through your goals,
> business data, and history — getting smarter every session.

## Concept

```
Input → Goal Filter → Knowledge Retrieval → History Check → Response
  ↑                                                          |
  ↓────────────────── Learning Harvest ──────────────────────┘
                         ↓
                    Qdrant (compounding)
```

## Components

1. **Goal Layer** — Personal and professional objectives (injected into context)
2. **Knowledge Layer** — Qdrant vector DB (cumulative knowledge)
3. **History Layer** — Past sessions (patterns, decisions, errors)
4. **Filter** — Every response filtered through these 3 layers

## Usage

### Before Each Session
```bash
python3 scripts/second-brain-context.py
```

### During Session (via Qdrant)
```bash
# Search accumulated knowledge
mcp_qdrant_qdrant_search_vault --query "similar problem encountered"

# Add a learning
# → memory(action='add', target='memory', content='Lesson learned: ...')
```

### After Each Session
```bash
python3 scripts/second-brain-harvest.py
```

## Key Properties

- **Compounding** — Each session adds to the knowledge base
- **Goal-aligned** — Objectives persist, not sessions
- **Zero LLM overhead** — Searches are vectorial (no tokens)
- **Local first** — Qdrant on EUREKAI (:6333), zero cloud
- **Context window savings** — Instead of re-injecting full history,
  retrieve only relevant memories via vector search

## Token Savings

| Approach | Context per Session |
|----------|-------------------|
| Naive: inject all history | 10,000+ tokens |
| Second Brain: vector retrieval | ~500 tokens |
| **Savings** | **~95%** |
