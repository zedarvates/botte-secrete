# Reddit — r/LocalLLaMA

**Titre :**
*I built a 4-layer local-first routing stack for AI agents — micro-NN (distilled, 0 tokens), deterministic NLP, local LLM, cloud. 138 tests, 78 skills, 65% token savings, GPG-signed, MIT.*

**Corps :**

After months of watching my agent burn tokens on tasks that didn't need a frontier model, I built a routing pipeline that pushes most work away from the cloud. Not by making models smarter — by making the *pipeline* cheaper.

**The 4-layer stack (cheapest first):**

| Layer | Tech | Cost | Example |
|---|---|---|---|
| 1. Micro-NN | 4 tiny distilled nets (numpy, ~5µs) | 0 tokens | "fix CSS layout bug" → effort 0.42 → route to tier 2 |
| 2. Deterministic | regex, gazetteers, OR-Tools solvers | 0 tokens | "extract function names from file" → regex, done |
| 3. Local LLM | LM Studio / Ollama | 0¢ | "refactor this function, add error handling" |
| 4. Cloud | DeepSeek, GLM, Claude | $$ | "design auth middleware, review security" |

Each layer abstains if unsure → escalates to the next. ~65% of my daily agent tasks never leave the machine.

**What's in the repo (78 skills):**
- **4 distilled micro-NN models** — trained on realistic corpora (not np.random), 4/4 grounded with provenance tracking. Binary router: 100% on held-out data. Effort classifier: 98%. Anomaly detector: 100%.
- **Code audit** — dead code, duplication, complexity, secrets, boundaries (Porthos/Blue Team)
- **Automated fixes** — with verification (d'Artagnan)
- **Red team** — adversarial agents that challenge the Blue Team (Cardinal pipeline)
- **Context profiler** — measures always-on prefix cost. On my Hermes setup: 52% of context is runtime overhead, not my project.
- **Auto-router** — effort-based task classification, escalation loop detection
- **MCP gateway** — 20+ tools exposed via stdio JSON-RPC, compatible with Claude Code, Cursor, any MCP client
- **Security scanner** — taint/data-flow, 30+ patterns, 8 categories, CWE-tagged
- **Control loop** — ledger records every routing decision, analyzes, adapts thresholds
- **`botte` CLI wrapper** — compresses terminal output by 60-99% before it enters agent context

**By the numbers:**
- 138 tests (51 e2e + 87 module), 0 failures
- 0 heavy ML deps — numpy + stdlib only
- GPG-signed commits (RSA 4096) — every commit verifiable
- GitHub Discussions enabled
- MIT license

**Honest caveats:**
- The distillation corpora are realistic but hand-curated (~50 examples/model). Real production data would improve the micro-NNs further.
- Control loop ledger is bootstrapped with 50 synthetic sessions — needs real agent sessions for production adaptation.
- The context profiler measures Hermes Agent overhead specifically. Other runtimes will differ.
- Some scanners produce false positives on sandbox/test code — reviewed and documented.

**One-command deploy:**
```bash
python -m skills.bootstrap.cli /your-project
```

Repo: https://github.com/zedarvates/botte-secrete

Happy to answer questions. Especially curious what other people are doing for local↔cloud routing in their agent pipelines.
