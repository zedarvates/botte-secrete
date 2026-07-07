# RTK nag "No hook installed" — documented workaround

The `rtk` Rust Token Killer prints "No hook installed" on every command
when the git hook isn't configured. This adds ~50 tokens to every terminal
output the agent reads.

## Fix (upstream / local)
```bash
# Suppress after first occurrence per session:
export RTK_SILENT=1

# Or install the hook once:
rtk init -g
```

## Botte workaround
The `botte` wrapper already suppresses this by default. Prefer `botte <cmd>`
over `rtk <cmd>` when both are available.

Tracked in: https://github.com/zedarvates/botte-secrete (this repo)
