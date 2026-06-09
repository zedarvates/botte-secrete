# Tiered Model Router (P14)
5-level intelligent model selection with cost estimation and auto-downgrade.

**Trigger:** Before EVERY LLM call — route through tiered router first.

**5 Levels:**
```
L0 FREE (0 tok):    Hailo-8, LocalAI TTS/STT, pure math/vectors
L1 LOCAL (~100 tok): LocalAI Gemma-4 / Ollama — simple Q&A
L2 CHEAP (~500 tok): Cloud small — code review, bug detection
L3 STANDARD (~2K tok): Cloud standard — architecture, complex reasoning
L4 PREMIUM (~8K tok): Cloud best — security audit, system design
```

**Features:**
- Cost estimation before call (tokens + $)
- Auto-downgrade when budget exceeded
- Per-project daily/monthly budget limits
- Usage tracking + savings report
- Agent-to-agent delta compression

**Module:** `skills/tiered_router`
**Typical savings:** 95-99% vs all-PREMIUM
