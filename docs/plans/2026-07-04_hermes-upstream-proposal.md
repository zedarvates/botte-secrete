# Hermes Agent — Upstream Integration Proposal

> Draft for posting to the Hermes Agent upstream repo.
> See `docs/plans/2026-07-02_hermes-upstream-proposal-draft.md` for the full version.

## What Botte Secrète offers to Hermes

Botte Secrète is a token-optimization platform that can be integrated as a Hermes
skill to reduce cloud token usage by ~65% on agent workloads. It provides:

1. **Micro-NN routing** — 4 trained feedforward networks (numpy, ~0ms) that classify
   effort, route local/cloud, detect anomalies, and classify errors. 0 cloud tokens.

2. **Deterministic NLP** — regex+gazetteer extraction, OR-Tools solvers for
   scheduling/assignment. 0 cloud tokens.

3. **Context profiler** — measures always-on prefix cost (directives, tool schemas,
   skill catalog, host overhead). Identifies the biggest token waste.

4. **Local harness** — structured output, verification, sandbox execution, and
   KV-cache-friendly prompt structuring for Ollama/LM Studio.

5. **Security scanner** — taint analysis, malicious pattern detection, CWE knowledge
   base (now with AI-agent-specific patterns: prompt injection, exfiltration).

## Integration points

- **MCP server**: Exposes 20+ tools via `llm_mcp` (route_task, local_chat, bench_run,
  doctor, fleet_status, etc.). Compatible with any MCP client.
- **Hermes bridge**: `hermes_bridge` skill maps Botte tools to Hermes tool schemas.
- **Skills**: 50+ self-contained skills (audit, fix, optimize, security, docs, infra).

## Token savings measured

- Always-on context: 8,120 tok (project) + 8,853 tok (host) = 16,973 tok total
- Reducible: 12,931 tok → 4,042 tok (lazy tools, on-demand skills)
- Host skill catalog alone: 5,720 tok (286 skills) — switch to find_skills pattern
- Micro-NN routing: ~65% cloud token reduction on eligible tasks

## Next steps

1. Human review of this proposal
2. Verify `hermes_bridge` against the real Hermes Agent repo
3. Post as a feature request / integration guide on the Hermes repo
