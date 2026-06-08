# Botte Secrète — Development Guide

## Philosophy

This repo follows the **subtraction principle**: the best optimization is removing
what you don't need, not adding what you might.

Every file, every script, every workflow in this repo exists to either:
1. **Reduce token consumption** in AI agent pipelines
2. **Improve code quality** through automated analysis
3. **Leverage local hardware** (Hailo-8, ComfyUI, Bonsai) to eliminate cloud costs

## Adding a New Module

1. Create a directory under `skills/<module-name>/`
2. Add a `README.md` or `RULES.md` explaining the module
3. Add scripts to `scripts/` if shared
4. Update the main `README.md` table
5. Update `docs/ARCHITECTURE.md`

## Code Rules

- **All READMEs in English** (hard rule from user)
- **No file > 2000 lines** (target: 1500)
- **stdlib first** — no dependency under 20 lines of utility
- **Verify before announcing** — never say "done" without testing

## Token Budget

When developing this repo itself, apply the same rules:
- Use `karpathy-review.py` on your own diffs
- Run `fallow` on JS/TS files
- Keep modules small and focused
- Prefer deletion over addition

## Hardware Development

### Hailo-8
- Test on EUREKAI (192.168.1.47)
- Models are `.hef` files — don't commit large binaries
- Use MCP server at port 8767

### ComfyUI
- Test on EUREKAI port 8188
- Workflow JSON files go in `workflows/comfyui/`
- Don't commit model weights

### Bonsai Image
- Runs locally via WebGPU
- Model: ternary Bonsai Image 4B (1.21 GB)
- Server at localhost:8788

## Testing

```bash
# Run all audits on this repo itself
./scripts/quick-audit.sh .

# Check hardware
python3 scripts/hardware_status.py

# Karpathy review
python3 scripts/karpathy-review.py --diff <(git diff HEAD~1)
```

## Release Process

1. Update version in `configs/version.txt`
2. Update `README.md` changelog
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`
