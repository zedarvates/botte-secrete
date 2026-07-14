# Botte Secrète TODO

## Release and integrations

- [ ] Merge and validate the cross-agent plugin pull request.
- [ ] Verify Codex, Cursor, Claude, OpenCode, Antigravity, Hermes, and OpenClaw
      adapters on clean machines.
- [ ] Add Windows, macOS, and Linux path-resolution tests.
- [ ] Document secret management for each supported agent.

## Loop Optimizer

- [ ] Collect 2,000 verified Botte trajectories before policy training.
- [ ] Train and evaluate a compact classifier with a temporal holdout.
- [ ] Require at least 10% token reduction without success-rate loss.
- [ ] Roll out only through the 10% → 50% → 100% staged gate.

## Maintenance

- [ ] Keep generated project MCP files out of public commits when paths are
      machine-specific.
- [ ] Run the full test suite, E2E tests, pre-commit checks, and checkup before
      every release.
