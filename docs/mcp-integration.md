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
