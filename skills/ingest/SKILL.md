---
name: ingest
description: Local-first web scraping and source ingestion — fetch a URL, extract clean text locally (0 cloud tokens), optionally structure it with a local model, and store it in a Qdrant collection (the second-brain "foundation") for later recall. Use for /web-scraping, /ingest-source, building a knowledge foundation, or recalling past ingested sources. Web fetch + Qdrant over stdlib HTTP.
---

# ingest — scrape the web & build a knowledge foundation, locally

Scraping and ingesting are extraction/transformation — keep them off the cloud.

```bash
python -m skills.ingest.cli scrape  https://example.com --structure   # local summary+entities
python -m skills.ingest.cli ingest  https://example.com --collection foundation
python -m skills.ingest.cli ingest  ./notes.md --file
python -m skills.ingest.cli search  "topic"  --collection foundation
```

- **scrape** — fetch (browser UA) + stdlib HTML→text (drops script/style, keeps
  title). `--structure` asks a LOCAL model for a 3-bullet summary + key entities.
  **0 cloud tokens.**
- **ingest** — scrape (or a file/raw text) → reflect locally → upsert into Qdrant
  (`192.168.1.47:6333` by default). Builds the "foundation"/historical store.
- **search** — recall from a collection.

Embeddings: deterministic hash n-gram (256-dim) by default, so it works with **no
embedding model**; point at a local `/v1/embeddings` endpoint for real semantic
recall. Degrades gracefully when Qdrant is down (scrape still works).

Exposed via [[llm_mcp]] as `scrape` and `ingest_source`. Related:
[[hermes-second-brain]] (the foundation concept), `media_loader`, [[auto_router]].
