# Security policy

## Report a vulnerability privately

Do **not** open a public GitHub issue for a suspected vulnerability.

Send a private report to `sylvain.galliez@gmail.com` with:

- the affected component and version or commit;
- a clear description of the issue and its impact;
- minimal reproduction steps or a proof of concept;
- whether credentials, private data, or remote systems may be affected;
- a suggested mitigation, if available.

Avoid sending live credentials or unnecessary personal data. Encrypt sensitive
details before sending when practical.

## Response targets

The project aims to:

- acknowledge a complete report within 48 hours;
- provide an initial assessment within 7 days;
- coordinate a fix and disclosure timeline based on severity and complexity.

These are targets for a maintainer-run project, not guaranteed service-level
agreements. Please allow time for safe reproduction and validation.

## Scope

This policy covers code and repository automation maintained in
`zedarvates/botte-secrete`, including:

- CLI and MCP input handling;
- bootstrap and configuration merging;
- local and remote model adapters;
- token, credential, path, and event-data handling;
- archive extraction and file-system boundaries;
- dependency and workflow configuration;
- dashboard sanitization and public artifacts;
- remote delegation and cluster communication.

Vulnerabilities in third-party agents, model servers, cloud providers, or
hardware are outside this repository's direct control, but reports are welcome
when Botte integrates with those systems unsafely.

## Supported versions

Security fixes target the latest code on the default branch and the most recent
published release line. Older prereleases and development snapshots may receive
only upgrade guidance.

## Security model

Botte is local-first, but local resources are not implicitly trusted.

- MCP arguments and model output are treated as untrusted input.
- Deterministic workflows do not require network access.
- Cloud providers and fresh remote checks are explicit operations.
- Credentials belong in environment variables or an approved secret store, not
  repository files.
- Remote delegation must bind the endpoint to the delegated host, use HTTPS
  outside loopback, and authenticate with an explicit token.
- Bootstrap merges existing MCP configuration instead of deleting it.
- Harvest is read-only and does not store raw file contents or patches.
- Public dashboard builds exclude local operational and memory metrics.

See [the architecture guide](docs/ARCHITECTURE.md) for trust boundaries and
[the development guide](docs/DEVELOPMENT.md) for secure contribution practices.

## Disclosure

Please keep vulnerability details private until a fix or mitigation is available
and a disclosure date has been coordinated. Credit will be offered unless the
reporter prefers to remain anonymous.
