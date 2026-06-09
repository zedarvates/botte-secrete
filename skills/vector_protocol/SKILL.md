# Vector Agent Protocol (P11)
Agents communicate via quantized embedding vectors, not human language.

**Trigger:** When multiple agents run in pipeline — use vectors for inter-agent comm.

**Principle:** Agents don't need to "understand" each other's text output.
They operate on 24-dimension vectors. Only the final orchestrator decodes to user language.

**Pipeline:**
```
Porthos → vectors (24 floats/finding) → Qdrant → d'Artagnan query vectors → Aramis → Athos (decode to French)
```

**Token savings:** -70% pipeline (no inter-agent text interpretation)

**Module:** `skills/vector_protocol`
**Vectors:** 24-dimension, quantized [0.0, 1.0]
**Backend:** Qdrant on EUREKAI:6333
