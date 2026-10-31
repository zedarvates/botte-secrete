# RTK — Rust Token Killer

> A terminal wrapper that compacts supported command output to cut token usage.
> Filtering is lossy: verify failure diagnostics and exit codes for the commands
> you use, and keep access to unfiltered output.

- Upstream: **https://github.com/rtk-ai/rtk**
- Reference release verified on **2026-09-13: v0.49.0**. This is not proof of
  the installed version or of Botte compatibility. Check yours with `rtk --version`.
- See the [external-tool inventory and update procedure](../../docs/external-tools.md)
  and [exact source references](../../configs/external-tools.json) before updating.
  Use a fixed release/commit rather than installing a moving upstream branch.

## Use it

Prefix commands (works inside `&&` chains too):

```bash
rtk cargo build         # build output, ~80% smaller
rtk cargo test          # failures only (~90%)
rtk git status          # compact status (~59%)
rtk git diff            # compact diff (~80%)
rtk pnpm install        # ~90%
rtk docker ps           # ~85%
rtk tsc                 # TS errors grouped by file/code
rtk lint                # ESLint/Biome grouped
```

## Categories & typical savings

| Category | Commands | Savings |
|----------|----------|---------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr/run/issue | 26-87% |
| Package managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |

## Meta commands

```bash
rtk gain         # token-savings stats
rtk discover     # find missed rtk usage in past sessions
rtk proxy <cmd>  # run without filtering (debugging)
rtk init         # add rtk guidance to CLAUDE.md
```

> Botte Secrète ships its own equivalent wrapper, `scripts/botte`, for use inside
> this repo. RTK is the general-purpose tool for everyday terminal work.
