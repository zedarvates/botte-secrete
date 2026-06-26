---
name: cwe_kb
description: Local CWE knowledge base (RAG) to enrich and de-noise security findings — match a finding (or any text) to the relevant weakness by exact id or local-embedding similarity, and attach the weakness name, description, and concrete mitigation. Deterministic, offline, 0 cloud tokens. Use to explain a CWE, find the likely weakness for a code snippet, or enrich taint/security findings with "why + how to fix".
---

# cwe_kb — local CWE knowledge base (RAG)

The DeepAudit idea, local-first: a small CWE catalog on disk + local-embedding
retrieval, so every security finding comes with *why it matters* and *how to fix
it* — **0 cloud tokens**.

```bash
python -m skills.cwe_kb.cli lookup CWE-78
python -m skills.cwe_kb.cli match "user input concatenated into a SQL query"
python -m skills.cwe_kb.cli enrich .        # taint scan + CWE context per finding
```

- **lookup(cwe_id)** — exact catalog entry (id/name/description/mitigation/common).
- **match(text, top_k)** — rank CWE entries by **local embedding** similarity
  ([[ingest]] embedding — real `/v1/embeddings` endpoint if available, deterministic
  hash otherwise — + [[vector_protocol]] cosine).
- **explain(cwe_id, text)** — exact by id, else best embedding matches.
- **enrich(findings)** — attach `cwe_info` (name, description, mitigation) to each
  taint/security finding: by the analyzer's CWE tag when present, else by matching
  the finding's message.

The catalog (`catalog.json`) is a curated subset: the CWEs the [[fallow_like]]
taint analyzer emits (78/89/94/502/918) plus common web/Top-25 weaknesses. Wired
into the `security_scan` MCP tool (findings come back enriched) and exposed as
`cwe_explain`. Completes the RepoAudit/DeepAudit-inspired security track: taint
finds the flow, the KB explains and prioritises it.
