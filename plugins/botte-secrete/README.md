# Botte Secrète Codex plugin

This version 1.11.0 plugin supplies one workflow skill and an MCP stdio connection.
Its executable runtime is installed separately; installing this plugin does not
install Python, Botte Secrète, optional dependencies, models or credentials.

## Install the local runtime

Use a checkout of Botte Secrète compatible with this plugin version. Install it
in the Python environment used by Codex, following the repository's dependency
instructions:

On Windows, use the Python interpreter available to Codex:

```powershell
python -m pip install "C:\path\to\botte-secrete"
```

On Linux or macOS:

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

A pinned Git ref remains pinned. Released versions identify immutable files;
publish a new semantic version when distributing changed files. In the tested
Codex CLI 0.159.2, reinstalling recopies a local source even at the same version.
Use the documented cachebuster flow below for local iteration.

For local development, update the checkout and replace the plugin manifest's
build suffix with a new UTC timestamp, such as
`1.11.0+codex.local-20261013-184516`. Keep the version prefix before `+`; replace
an existing suffix instead of appending another one. This changes the local
Codex cache key without incrementing the release version for each edit. The
committed release manifest stays at `1.11.0`.

Confirm that the selected marketplace is the local checkout you edited, then
run `codex plugin add botte-secrete@botte-secrete-marketplace` again. Marketplace
upgrade is for Git sources. Start a new Codex thread after the update. See the
[official local-update reference](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/plugin-creator/references/installing-and-updating.md)
for the plugin-creator skill's timestamp helper and cachebuster policy.

This Git marketplace is separate from the universal public ChatGPT/Codex plugin
directory. Public directory submission of an MCP plugin requires its own supported
server deployment and review; a local stdio server is not a completed public
directory submission.

Official format references, checked 2026-10-13:

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Plugin MCP package example](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins)
- [Listing field types and limits](https://developers.openai.com/plugins/deploy/submission-errors)

From the repository checkout, run `python -m skills.plugins.test_distribution`
to check the listing capabilities, starter prompts, square SVG icons, package files and MCP
handshake. These checks cover the Git package and selected listing constraints.
They do not complete public directory submission or its MCP deployment, URL,
review requirements. The two geometric boot icons are original assets included
under the packaged MIT license.
