# Botte Secrète MCP integration

Botte Secrète exposes one local stdio MCP server:

```text
python -m skills.llm_mcp.server
```

The server is local-first. It provides routing, local chat, skill discovery,
loop decisions, cache-aware helpers, and diagnostics. It does not require a
cloud key for local operations.

## Install adapters

```bash
python -m skills.plugins.cli /path/to/project
```

The installer preserves existing servers and writes native project adapters:

| Agent | Configuration |
|---|---|
| Claude Code | `.mcp.json` |
| Cursor | `.cursor/mcp.json` |
| OpenCode | `opencode.json` |
| Codex | `.codex/config.toml` |
| Antigravity | `.gemini/antigravity/mcp_config.json` |
| Hermes | `.hermes/config.yaml` |
| OpenClaw | `.openclaw/openclaw.json` |

Use `--tools` to install a subset. Restart the agent after changing its
configuration, then inspect the MCP server list before using tools.

## Read the installation diagnostic

Run `python -m skills.checkup.cli /path/to/project --json` to inspect
`mcp_wiring`. This is a static inspection of project adapter files, not a
connection test. `configured` means a supported declaration has a valid shape;
it does not mean that the plugin is installed in the current host or that its
server can start. Launcher lookup uses the checkup process environment, which
may differ from the host's environment. Runtime and reachability remain
`not_checked` until the host actually connects.

Malformed, disabled, unreadable and unsupported configurations remain visible.
On Python 3.10, TOML inspection is unsupported without the standard-library
`tomllib` introduced in Python 3.11. Hermes YAML inspection is unsupported here.
User-level configuration and installed plugin caches are outside this
project-only inspection. For those, inspect the host's own MCP status and make
a read-only tool call. Keep configuration, launcher discovery, a protocol
handshake and successful task execution as separate observations.

## Bounded tool discovery

Lazy mode already lists a small core plus `find_tool`; setting
`BOTTE_MCP_LAZY_TOOLS=0` retains the full-list compatibility mode. Non-core
registered tools remain callable by name in either mode.

`find_tool` now ranks an exact identifier first and breaks score ties by name,
independently of registration order. Accent normalization helps matching supplied
names/descriptions; it does not translate French requests into English.

```json
{"query":"review_knowledge_links","top_k":5,"schema_budget_bytes":8192}
```

The cumulative schema budget defaults to 8192 bytes (range 0–65536), counting
compact UTF-8 JSON for included `inputSchema` objects only. It does not cap the
whole response or measure provider tokens. Each returned description is limited
to 384 UTF-8 bytes, with an explicit truncation flag. Queries are limited to
2048 UTF-8 bytes and `top_k` to 1–10. Invalid types and unsupported arguments
return an MCP tool error and leave the server available for the next request.

A strong match carries its complete schema when it fits. Otherwise its name
remains visible with `schema_status: deferred_budget`; smaller following matches
can still fit. Increase the budget within its bounds for an explicit lookup.
Weak matches remain hints and missing schemas remain `unavailable`. A zero
schema budget permits discovery by names/descriptions only. Returned schemas
are independent copies of the registered definitions.

Discovery makes no backend probe or model call. A registered tool is not proof
that LM Studio, Ollama, Godot or a remote worker is available. Keep installation,
connection and successful execution separate, as above. This change does not
activate a model route or alter the cloud connector.

### Optional compact index

For broad discovery, call `find_tool` with `detail: "index"`. This explicit view
returns the same ranked tool identifiers as the default search, plus descriptions
limited to 160 UTF-8 bytes. Truncated descriptions are marked. It returns
`schema: "botte.tool-discovery-index/v1"` and `schemas_included: false`, without
serializing any tool schemas. The default `detail: "schemas"` behavior remains
unchanged.

The index is a lossy discovery hint, not instructions, authorization or an
executable tool definition. Before calling a selected tool, resolve its exact
identifier with `detail: "schemas", top_k: 1` and check the complete schema and
applicable guidance. A schema still exceeding the requested byte budget stays
deferred. No tool is executed by either discovery step.

This two-step path adds a roundtrip. Prefer the existing single lookup for a
known identifier or small response; do not enable index mode globally based on
byte counts alone. `python scripts/measure_discovery_index.py` reproduces a
six-query authored comparison via the actual stdio server, counting requests
and responses for both lookups. It checks identifier retention and exact selected
schema recovery, not semantic relevance or task success. Four of the six sample
queries are larger in index mode; provider cost and latency remain unmeasured.
See [the sample measurement](validation/gg-discovery-index-2026-10-31.json).

This extends the existing loader, inspired by GG Framework's deferred schemas
and budget checks (revision `12eb9ea52c239ebd4843367e2c60bd45a9b4eeef`):
[tool tiers](https://github.com/KenKaiii/gg-framework/blob/12eb9ea52c239ebd4843367e2c60bd45a9b4eeef/packages/ggcoder/src/tools/tool-tiers.ts)
and [tool search](https://github.com/KenKaiii/gg-framework/blob/12eb9ea52c239ebd4843367e2c60bd45a9b4eeef/packages/ggcoder/src/tools/tool-search.ts).
No upstream implementation is copied. Regression checks:
`python -m skills.llm_mcp.test_lazy_budget` and the existing
`python -m skills.llm_mcp.test_lazy`.

## Safety and troubleshooting

- Keep generated configurations local when they contain absolute paths.
- Never put API keys in these files; use the agent’s secret store or environment.
- If a server is not visible, verify the configured interpreter and working
  directory, then run the agent’s own MCP doctor/status command.
- OpenClaw supports static checks with `openclaw mcp doctor`; Hermes provides
  `hermes mcp catalog` and configuration commands.
- The Botte Loop Optimizer remains in `shadow` mode by default and Needle is
  disabled by default.

Official references: [Claude Code MCP](https://code.claude.com/docs/en/mcp),
[Cursor MCP](https://docs.cursor.com/context/model-context-protocol),
[Codex configuration](https://github.com/openai/codex/blob/main/docs/config.md),
[Hermes MCP](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md),
and [OpenClaw MCP](https://docs.openclaw.ai/cli/mcp).
