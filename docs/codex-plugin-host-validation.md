# Qualify the plugin inside Codex

The clean runtime installation checks and this host check prove different parts
of the setup. A direct MCP client can verify server behavior without proving
that Codex discovered the plugin, loaded its skill or connected its bundled MCP.

The `Codex plugin host qualification` workflow uses a fresh hosted runner on
Ubuntu and Windows, Python 3.12 and the pinned public Codex release `0.166.0`.
It builds the candidate wheel from the exact PR head and installs the runtime
in a new virtual environment. The profile is the runner's native fresh profile;
the workflow does not redirect `HOME` or `CODEX_HOME`.

The probe refuses to start if that profile already contains Codex configuration,
authentication or plugin installations. It then uses the real CLI commands to
register the local marketplace and install `botte-secrete`. These commands write
only to the disposable runner profile. No active user profile is installed or
enabled by this qualification.

## Official 1.11.1 catalog

The plugin explicitly sets `BOTTE_MCP_LAZY_TOOLS=0`. Codex receives the complete
tools/list catalog and can register specialized methods before any call. The
host probe asserts that each selected method and its schema are already offered.
It does not treat a find_tool text response as native method registration.
Historical reports that exercised compact discovery remain historical evidence.

## Acceptance criteria

- The host reports the plugin as installed and enabled in the expected local
  marketplace. Its bundled MCP server is declared.
- The plugin skill is enabled and has the matching `pluginId`. Its installed
  cache files match the candidate source. A qualified skill name returned by
  Codex is kept distinct from the unqualified manifest/frontmatter name.
- An ephemeral read-only thread connects the MCP server belonging to that
  `pluginId`. No standalone MCP configuration is injected as a substitute.
- Three authored scenarios run through Codex's app-server MCP-call endpoint:
  statistics, exact file duplicates and supplied Markdown links. The probe
  reuses the independently checked fixtures from the runtime installation
  harness, including invalid inputs and partial results.
- A second host process without `botte-mcp` on its PATH must observe the bundled
  server as unavailable. An already configured or cached standalone server must
  not produce a false pass.

The app-server client's method allowlist excludes `turn/start`. This check does
not submit a prompt to a model. It qualifies installation, skill discovery,
transport and controlled tool execution; automatic skill selection and model
tool choice on unseen requests remain separate evaluations.

Reports record the candidate commit, wheel hash, installed module provenance,
actual Codex version, plugin/cache/skill evidence, server owner and transport
state, scenario outcomes, bounded protocol byte counts and elapsed time.
Provider tokens, cost and savings remain unknown. A host-protocol call is not
a measurement of a complete model-driven task.

Scenario timers start after the host thread and MCP connection are ready.
Protocol byte counts cover the Codex app-server channel, not only MCP payloads.
The overall probe timer includes its verification and CLI installation steps,
but excludes wheel build, runtime installation and Codex package installation.
These intervals differ from the direct-runtime probe and must not be compared
as a speedup or transport overhead measurement.

## Local managed environment

A local smoke check used a filesystem namespace with a read-only root and a
temporary directory mounted over the normal profile path. The environment
variable values were unchanged. Codex `0.166.0-alpha.1` verified installation,
cache materialization and plugin skill discovery there. The managed environment
could not start the thread's nested read-only sandbox helper; this is a partial
local observation, not a completed MCP host qualification. The public stable
release is qualified independently by the fresh-runner workflow.

The local profile test does not relax the managed host's requirements. A failed
or incomplete host report remains a failed or incomplete qualification.

## Reproduce

Use the exact reviewed candidate commit for the runtime and plugin. The workflow
is the reproducible entry point; it uploads `codex-host-report.json` and the wheel
for each native platform. Check both job conclusion and report status.

For an already disposable, empty profile, run the probe from outside the source
checkout using the installed runtime's Python. Pass the source checkout,
Codex binary, full commit SHA and exact built wheel through its explicit CLI
arguments. Include `--negative-runtime` for the unavailable-command witness.
The probe is not a command for an existing personal Codex profile.

Format and CLI references checked on 2026-10-30:

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [OpenAI harness-aware plugin evaluation](https://developers.openai.com/cookbook/examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals)

This workflow does not publish to a directory, merge the candidate, deploy the
cloud service or add Custom Desktop integration.
