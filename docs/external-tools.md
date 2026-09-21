# External tools: RTK and Ponytail

Botte's Python package does not install or update these tools. RTK is an optional
external CLI. Botte's [decision ladder](../skills/decision_ladder/SKILL.md) is a
separate Python implementation inspired by Ponytail, not a bundled Ponytail
plugin. Its own version must not be reported as the upstream Ponytail version.

## Reference versions

The dated [reference manifest](../configs/external-tools.json) records upstream
releases observed on **2026-09-13**, including their exact commits:

| Tool | Reference release | Publication date | Botte integration compatibility |
|---|---|---|---|
| RTK | [0.49.0](https://github.com/rtk-ai/rtk/releases/tag/v0.49.0) | 2026-09-11 | Not tested |
| Ponytail | [4.9.0](https://github.com/DietrichGebert/ponytail/releases/tag/v4.9.0) | 2026-08-07 | Not tested |

These are release references, not an installation lock, a live update feed, or
proof of the versions installed on any user's machines. Do not mark a reference
compatible merely because the Botte test suite is green.

## Inventory each environment

From a checkout, run with the same user and environment as the coding agent:

```bash
python scripts/inventory_external_tools.py --machine-label workstation
```

RTK is located on this process's PATH and invoked with `--version` only (five
second timeout). Use `--rtk-binary` to inspect a specific executable. A terminal
alias or another agent's PATH may resolve differently. `not_found_on_path` does
not establish that the machine has no RTK installation.

Ponytail installations belong to individual agent/plugin managers. Supply the
installed package or plugin root, with the real path on the target machine:

```bash
python scripts/inventory_external_tools.py --machine-label workstation --ponytail-root "PATH_TO_INSTALLED_PONYTAIL"
```

Repeat `--ponytail-root` to inspect multiple installations separately. The script
reads only `package.json`, `.claude-plugin/plugin.json`, and
`.codex-plugin/plugin.json` under the supplied roots. It verifies declared package
names and records metadata SHA-256 values. Malformed or inconsistent metadata is
reported as unknown/conflicting; an omitted root is `not_checked`. Instruction
copies and other layouts without these manifests remain unverified.

The inventory never executes Ponytail, installs packages, initializes hooks, or
changes an agent configuration. The RTK subprocess is the existing executable's
version command; the script does not sandbox that executable. Metadata hashes
identify the files read, not the integrity of the whole installed plugin.

JSON goes to stdout; save it privately under the already ignored `.botte-cache/`
directory if needed. Reports include machine labels and absolute local paths and
must not be committed. Exit code zero means the report completed: inspect each
`version_status`, not just the process exit code. `matches_reference` certifies
neither agent activation nor compatibility. Prerelease/build suffixes require
manual review and are not silently treated as a stable version.

## Bounded update procedure

1. Inventory the current installation and preserve its package/configuration for
   rollback. Identify which coding agent actually uses each installation.
2. Test the reference release in an isolated installation, using the exact commit
   in the manifest or a verified upstream release asset. Avoid an unpinned Git
   branch or a floating package version. Do not register global hooks to test it.
3. For RTK, exercise the commands used by that agent, checking failure exit codes,
   useful diagnostics, and raw-output recovery. For Ponytail, verify instruction
   and hook loading with the specific agent and check for duplicate instructions
   alongside Botte's decision ladder. Record the OS, agent version, tool version,
   commands, and results; a Windows-shaped mocked path is not a Windows run.
4. Update only that installation after its checks pass, then repeat the inventory
   and Botte checkup. Keep other machines explicitly unverified until observed.

The current change provides the inventory and source references only. It records
no homelab installation, upstream integration test, activation, or deployment.
