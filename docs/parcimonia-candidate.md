# Parcimonia consolidated candidate

This validation branch combines task assessment and GitHub evidence helpers,
portable project/plugin guidance, deterministic statistics, exact-file duplicate
inspection and supplied Markdown link checks. It is an unreleased candidate;
the branch does not merge or activate the separate draft changes on `main`.

## Select one immutable source

Use the full reviewed commit SHA from the candidate pull request for both the
Python runtime and the Git marketplace package. Version `1.11.0` alone does not
identify the candidate: several draft commits use this unreleased version.
Do not use `main` to install the candidate features.

Follow the [plugin runtime installation guide](../plugins/botte-secrete/README.md)
for your operating system, using a checkout detached at that reviewed SHA.
The independently installed runtime must provide `botte-mcp` on the PATH used
by Codex. The plugin itself does not install Python or runtime dependencies.

The candidate PR supplies its exact pinned installation reference. The
marketplace and runtime must come from that same reference. Repository package
checks and a working MCP executable do not establish that a particular Codex
host has loaded the plugin, selected its skill or run its tools automatically.

## Clean-install qualification

The `Parcimonia candidate installation` workflow checks out the exact PR head,
builds a wheel from the full repository, creates a new virtual environment with
no system packages, and installs that wheel. It runs the harness with Python
isolated mode from outside the source checkout, without `PYTHONPATH` or
`PYTHONHOME`. The exercised installed modules must match the wheel contents and
source files by SHA-256. Reports include the source SHA and wheel SHA-256.

| Installation | Platforms | What it establishes |
| --- | --- | --- |
| Minimal, dependencies omitted | Ubuntu and Windows; Python 3.10 and 3.12 | The selected deterministic workflows run without the wheel's declared dependencies. This does not qualify every Botte tool. |
| Normal dependency installation, followed by `pip check` | Ubuntu; Python 3.12 | The built wheel and its declared dependencies install together, then the same three workflows pass. Other tools remain outside these scenarios. |

The harness starts the console executable selected by the plugin's stdio
configuration. It performs an MCP handshake, observes lazy tool discovery,
assesses each authored task with the actual exposed tool metadata, executes the
selected tool and checks its result independently:

1. Statistics: mean and the specified 95th percentile are checked against known
   values; invalid numeric input must be rejected.
2. File duplicates: temporary copies and distinct content are checked, hard
   links are distinguished where supported, and input bytes remain unchanged.
   A limited scan must remain partial.
3. Markdown links: supplied paths and documents produce the expected existing
   and missing targets with source lines. An incomplete inventory must produce
   unresolved targets, never a definitive missing conclusion.

A negated task must abstain. Project guidance is checked on temporary
projects, including preservation of user policy and existing agent instructions.
These are controlled qualification scenarios, not measurements of how often a
model or a real user chooses the right tool on unseen requests.

The workflow uploads the wheel, `installation.json` and `candidate-report.json`
for each job. An upload alone is not a pass: inspect the job conclusion and
report result. A smoke run built from a selected local source snapshot is kept
distinct from full-repository qualification.

## Interpret measurements

The installation record measures wheel build and install duration. The harness
measures actual stdio process startup/handshake and each scenario's discovery,
assessment, execution and fixture checks, with actual protocol UTF-8 byte counts.
It records failures and the tested environment. These are individual observations
subject to machine and runner load, not portable latency guarantees.

Provider tokens, billed cost and savings remain `null`: no paid model baseline
is run. A lower measured JSON size is not a token count. A gain claim requires a
paired baseline with the same task, revision, success criteria, tool availability,
and all host calls, retries and fallbacks included.

## Distribution boundaries

The additional [Codex host qualification](codex-plugin-host-validation.md)
checks plugin installation, skill discovery and controlled MCP execution through
the real app-server on fresh profiles. Its results are separate from the direct
runtime installation matrix above; neither establishes automatic model choice.

| Capability | Candidate Python runtime | Independently hosted cloud |
| --- | --- | --- |
| Statistics on supplied values | Included and qualified by the installation scenarios | Existing separate deployment; not changed by this branch. |
| Exact file duplicates | Inspects the explicitly supplied local root | Requires local file access; no cloud scan of the user's disk is provided. |
| Markdown links against supplied inventory | Included, without filesystem access | Suitable for a separate port and validation; not deployed by this branch. |
| Plugin/project guidance | Included as repository files and installed package data | Does not activate a host hook or guarantee skill selection. |

Custom Desktop by kelpie-dev remains roadmap-only until its project link is
supplied. This candidate adds no desktop customization integration.
