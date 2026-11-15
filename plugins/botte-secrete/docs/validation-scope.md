# Validation scope for the 1.11.1 delivery

This guide is bundled with the plugin so the standalone marketplace archive
does not depend on a repository-level documentation directory.

Version 1.11.1 is a local corrective delivery for plugin documentation and
version metadata. Archive verification and release preparation do not publish
the package, replace the active runtime or qualify every supported platform.
Use the accompanying delivery manifest and validation report for the exact
source revision, local changes, tested checks and SHA-256 archive identities.

## Historical qualification and current checks

The repository's historical Parcimonia qualification exercises three bounded
workflows: supplied-value statistics, exact local-file duplicates, and Markdown
links against an explicit path inventory. Historical receipts identify their
own revisions and environments; their results must not be relabelled as new
1.11.1 test executions.

Current delivery checks must use the actual source, wheel and marketplace
inventories. In particular, a link present in the full repository can still be
absent from the standalone plugin archive. Check all bundled Markdown documents
against the files that will actually be distributed, including these guides.

A successful MCP handshake establishes a protocol connection. A successful
tool call establishes that operation on the supplied data. Neither proves
automatic skill selection, a clean installation on every platform, activation
of learned policies, or a gain in quality, billed tokens or cost.

See the bundled [MCP diagnostics](mcp-diagnostics.md) for configuration and
runtime checks, or return to the [plugin guide](../README.md).
