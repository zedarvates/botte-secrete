# Botte Secrète Codex plugin

This version 1.11.1 plugin supplies one workflow skill and an MCP stdio connection.
Its executable runtime is installed separately; installing this plugin does not
install Python, Botte Secrète, optional dependencies, models or credentials.

This package is part of Botte Secrète 1.11.1. Use the runtime wheel and marketplace
from the same official release or full reviewed commit. The delivery manifest
binds the exact source files, archives and validation reports.

## Install the official release

Install the 1.11.1 runtime wheel from the GitHub release in a dedicated Python
environment, and make its botte-mcp command available on Codex's PATH. Register
the marketplace at the release tag, then install this plugin:

```sh
codex plugin marketplace add zedarvates/botte-secrete --ref v1.11.1
codex plugin add botte-secrete@botte-secrete-marketplace
```

If a marketplace with this name already points to a local override or another
ref, inspect it and replace only that Botte source before installing. Existing
conversations may retain their current server connection; verify the installed
version and native specialized methods in a fresh Codex conversation.

## Direct native tools

The bundled .mcp.json sets BOTTE_MCP_LAZY_TOOLS=0 for the botte-llm process.
The complete tools/list catalog is advertised at initialization, so Codex can
register specialized tools and their schemas as native methods. Call the actual
compute_statistics, find_file_duplicates and check_local_links methods offered
by the host. Optional tools retain their backend and authorization prerequisites.

The runtime's compact mode remains available to other clients. find_tool returns
text and schemas; it does not register methods in Codex. This official plugin uses
the complete catalog and needs no separate stdio client for specialized calls.
No model, permission or automatic execution is enabled merely by listing tools.

## Reproduce a reviewed candidate

Choose the full 40-character commit from the reviewed pull request, including
the state of its checks. Replace `REVIEWED_FULL_COMMIT_SHA` and `ABSOLUTE_CHECKOUT`
below. These placeholders are deliberately not a moving branch or an invented
release tag. Keep the same commit in both the Git checkout and marketplace:

```sh
git clone --no-checkout https://github.com/zedarvates/botte-secrete.git ABSOLUTE_CHECKOUT
git -C ABSOLUTE_CHECKOUT fetch origin REVIEWED_FULL_COMMIT_SHA
git -C ABSOLUTE_CHECKOUT checkout --detach REVIEWED_FULL_COMMIT_SHA
git -C ABSOLUTE_CHECKOUT rev-parse HEAD
python3 -m pip install ABSOLUTE_CHECKOUT
codex plugin marketplace add zedarvates/botte-secrete --ref REVIEWED_FULL_COMMIT_SHA
codex plugin add botte-secrete@botte-secrete-marketplace
```

On Windows, use `python -m pip` and an absolute Windows checkout path. Inspect
`codex plugin marketplace list` and confirm that the selected source is pinned
to the chosen SHA before installing; an existing `main` registration is not that
pin. A previously pinned source remains pinned until explicitly changed.

Make the installed environment's `botte-mcp` available on Codex's PATH. In a new
Codex conversation, verify the server's reported package version, available
schemas and a read-only `assess_task` call. The version alone is insufficient
when several unreleased commits share it; retain the reviewed source SHA too.
For local cache iteration, use the timestamp procedure in the Update section.
This recipe is an installation procedure, not evidence that a fresh install has
already passed on every platform.

For the distinction between delivery checks and the historical three-workflow
qualification, see the bundled [validation scope](docs/validation-scope.md).
The project checkup now separates a configuration declaration from launcher
discovery and runtime reachability. Its static `configured` result does not
qualify the plugin installed in Codex; use Codex's current server status and
the read-only call above. See the bundled [MCP diagnostics](docs/mcp-diagnostics.md#read-the-installation-diagnostic)
for supported files and parser limitations.

## First-assessment behavior

The plugin skill can now be selected for research, tool choice, code work and
test planning without an explicit Botte mention. The host decides which skills
to load; the package does not force every conversation through a helper. Reuse
a supplied assessment, and skip extra calls for trivial or obvious direct work.

The separate project preflight hook calls Parcimonia locally where that hook is
installed. Its current integration is Claude Code's `UserPromptSubmit`; the
Codex plugin ships no lifecycle hook, and Work cloud does not run that local
hook. Cloud use relies on connected tools and workflow instructions instead.

The bundled workflow skill includes Parcimonia assessment before substantive
work, reuse for homogeneous batches and a fallback when helpers are absent or
abstain. These instructions travel with the plugin; no personal skill or global
hook is required. They guide the host and do not demonstrate that an assessment
has run; they apply when the host loads or invokes the skill. Repository users also receive `AGENTS.md` and `.botte/policy.md`; the
bootstrap carries that guidance into newly configured projects.

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
`1.11.1+codex.local-20261031-184516`. Keep the version prefix before `+`; replace
an existing suffix instead of appending another one. This changes the local
Codex cache key without incrementing the release version for each edit. The
release manifest stays at `1.11.1`.

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
