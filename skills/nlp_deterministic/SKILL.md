---
name: nlp_deterministic
description: Classify and extract from text WITHOUT an LLM — intent classification (lexical overlap + local embedding), entity extraction (regex/gazetteers for urls/emails/ips/paths/env vars/flags/numbers), and stopword-filtered keyword frequency. Deterministic, instant, 0 cloud tokens. Use instead of asking a model to classify text or extract entities, and as the routing/intent layer that keeps cheap language decisions off the LLM.
---

# nlp_deterministic — classify & extract without a model

Many "ask the model to classify / extract" calls don't need a model: a rule +
gazetteer + local-embedding pass is **deterministic, instant, 0 cloud tokens**.
This is the NLP half of the determinism program (alongside the combinatorial
solvers): replace LLM reasoning for structured language decisions with exact,
repeatable computation.

```bash
python -m skills.nlp_deterministic.cli classify "speed up my SQL" perf=fast,optimize,slow auth=login,token
python -m skills.nlp_deterministic.cli entities "GET https://x.io from 10.0.0.1 with $TOKEN --json"
python -m skills.nlp_deterministic.cli keywords "cache the cache so queries stay fast"
```

- **classify(text, intents)** — `intents = {label: [keywords]}`. Score = keyword
  recall blended with a local hash-embedding cosine ([[ingest]] embedding +
  [[vector_protocol]] cosine, offline). Returns the best label + per-label scores.
- **extract_entities(text)** — regexes for urls, emails, IPs, file paths, env
  vars (`$VAR`/`%VAR%`), CLI flags (`--flag`), and numbers.
- **keywords(text)** — stopword-filtered (EN+FR) frequency keyphrases.

Exposed via [[llm_mcp]] as `nlp_classify` and `nlp_extract`. Pairs with
[[auto_router]] (effort/intent before routing) and [[skill_finder]]. Deterministic
classification is the cheapest possible routing/triage layer — 0 tokens, always
the same answer.
