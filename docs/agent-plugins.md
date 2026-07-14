# Agent plugins

Botte Secrète exposes one local MCP server and can install the native project
configuration for seven coding agents:

```bash
python -m skills.plugins.cli /path/to/project
python -m skills.plugins.cli /path/to/project --tools codex cursor
```

The installer is non-destructive: existing MCP servers are preserved and the
`botte-llm` entry is updated in place. It writes project-local adapters for
Claude Code (`.mcp.json`), Cursor (`.cursor/mcp.json`), OpenCode
(`opencode.json`), Codex (`.codex/config.toml`), Antigravity
(`.gemini/antigravity/mcp_config.json`), Hermes (`.hermes/config.yaml`), and
OpenClaw (`.openclaw/openclaw.json`).

Generated files contain local interpreter and path information. Keep them out
of public commits unless the paths are portable for the target team.
