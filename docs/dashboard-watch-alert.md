# Dashboard --watch alert

When watching the dashboard in live mode, ANSI bell alerts on escalation:

```python
# In dashboard/render.py, add after escalate detection:
if event.get("kind") == "escalate":
    print("\a", end="", flush=True)  # ANSI bell
```

CLI usage:
```bash
python -m skills.dashboard --watch --alert
```

The `--alert` flag enables ANSI bell (\\a) + red flash on escalation events.
Disabled by default to avoid noise in automated pipelines.
