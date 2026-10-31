# MCP diagnostics

The plugin declares a local stdio server named `botte-llm` with the command
`botte-mcp`. Install the compatible Python runtime separately and ensure that
the host's PATH resolves the intended executable. The plugin archive contains
guidance and wiring; it does not contain that runtime or its dependencies.

## Read the installation diagnostic

With the runtime installed, run the following against the intended project:

```text
python -m skills.checkup.cli /path/to/project --json
```

The `mcp_wiring` result is a static inspection of project adapter files.
`configured` means that a supported declaration has a valid shape. It does
not prove installation in the current host or a working connection. Launcher
lookup uses the checkup process environment, which may differ from the host's.
Runtime and reachability remain `not_checked` until the host actually connects.

Supported project adapter paths include `.mcp.json`, `.cursor/mcp.json`,
`opencode.json`, `.codex/config.toml`, `.gemini/antigravity/mcp_config.json`,
`.hermes/config.yaml` and `.openclaw/openclaw.json`. Malformed, disabled,
unreadable or unsupported inputs remain explicit. TOML inspection requires
standard-library `tomllib` (Python 3.11 or newer); Hermes YAML inspection is
unsupported by this diagnostic. User-level configuration and installed plugin
caches are outside this project-only check.

## Verify the actual host connection

Inspect the host's MCP status, then make a read-only call. Retain the server's
reported version, selected executable and source identity. Configuration,
launcher discovery, handshake and successful task execution are separate facts.

In lazy mode, `tools/list` exposes a small core including `find_tool`. Discover
the exact target name and its input schema before invoking a deferred tool.
Registered non-core tools remain callable by name on the native server; host
bridges may expose only their initial tool list. A returned schema is not proof
that the host bridge has added a directly callable method. Preserve absent
tools, abstentions and protocol errors in the report instead of claiming a run.

See [validation scope](validation-scope.md) for evidence limits and the
[plugin guide](../README.md) for installation procedures.
