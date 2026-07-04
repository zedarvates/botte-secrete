# README screenshots — planned captures

For GitHub README visual appeal:

1. **checkup output**: `python -m skills.checkup.cli .` — the main dashboard
2. **context_profiler --host**: shows the host/project breakdown
3. **auto_router --explain**: detailed routing trace
4. **nn_audit**: 4/4 grounded display

## How to generate

```bash
# Using asciinema (optional, not a dependency)
asciinema rec demo.cast -c "python -m skills.checkup.cli ."
asciinema play demo.cast

# Static screenshot via terminal
script -q -c "python -m skills.checkup.cli ." /tmp/checkup.txt
```

The HTML dashboard at `http://localhost:7000/proxy/8787/` can be captured
with any browser screenshot tool.
