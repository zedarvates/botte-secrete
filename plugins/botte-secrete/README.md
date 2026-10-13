# Botte Secrète Codex plugin

This version 1.10.0 plugin supplies one workflow skill and an MCP stdio connection.
Its executable runtime is installed separately; installing this plugin does not
install Python, Botte Secrète, optional dependencies, models or credentials.

## Install the local runtime

Use a checkout of Botte Secrète compatible with this plugin version. Install it
in the Python environment used by Codex, following the repository's dependency
instructions:

```sh
python3 -m pip install /absolute/path/to/botte-secrete
```

Make that environment's `botte-mcp` console executable available on Codex's PATH.
The MCP server uses stdio and must keep protocol messages on stdout. No working
directory, shell expansion or project-relative Python module is assumed by this
plugin's MCP configuration. Optional workflows may need local model services or
additional dependencies; inspect the runtime's available tools before using them.

## Install in Codex

For a public Git marketplace source:

```sh
codex plugin marketplace add zedarvates/botte-secrete --ref main
codex plugin add botte-secrete@botte-secrete-marketplace
```

For a local checkout, replace the first command with:

```sh
codex plugin marketplace add /absolute/path/to/botte-secrete
```

The source path `./plugins/botte-secrete` resolves from the marketplace root,
not from its `.agents/plugins/` directory. Start a new Codex session and check
that the `botte-llm` MCP server exposes its tools. A missing `botte-mcp` command
means the runtime environment still needs setup.

## Update

Upgrade the separately installed runtime to the compatible version. For a Git
marketplace, refresh the source and reinstall the plugin:

```sh
codex plugin marketplace upgrade botte-secrete-marketplace
codex plugin add botte-secrete@botte-secrete-marketplace
```

A pinned Git ref remains pinned. For a local marketplace, edit/update the checkout
and use `codex plugin add` again; marketplace upgrade is for Git sources. Start
a new Codex session after the update.

This Git marketplace is separate from the universal public ChatGPT/Codex plugin
directory. Public directory submission of an MCP plugin requires its own supported
server deployment and review; a local stdio server is not a completed public
directory submission.

Official format references, checked 2026-10-13:

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Plugin MCP package example](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins)
