# RTK — Real-Time Token Keeper

> Terminal command rewriting and output compaction for token savings.

## Modes

| Mode | Behavior | Savings |
|------|----------|---------|
| `rewrite` | Rewrites commands before execution | ~30% |
| `suggest` | Suggests shorter alternatives | ~15% |
| `aggressive` | Rewrites commands + compacts output | ~50% |
| `off` | Disabled | 0% |

## Usage

```bash
# Check status
/rtk status

# Set mode
export RTK_HERMES_MODE=aggressive

# View stats
/rtk stats
```

## Custom Backends

RTK supports dedicated compactors for:
- `hailo` — Hailo-8 CLI commands
- `docker` — Docker compose/output
- `comfyui` — ComfyUI API calls
- `kubectl` — Kubernetes commands

## Cache

LRU cache with 128 entries avoids re-rewriting frequent commands.

## Integration

```bash
# In .bashrc or .zshrc
export RTK_HERMES_MODE=rewrite
eval "$(rtk init)"
```

## Stats Output Example

```json
{
  "commands_rewritten": 142,
  "tokens_saved": 8520,
  "cache_hit_rate": 0.73,
  "avg_compaction_ratio": 0.68
}
```
