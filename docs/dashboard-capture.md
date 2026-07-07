# Dashboard HTML TUI capture

The dashboard at http://localhost:7000/proxy/8787/ can be captured:

## Static screenshot
```bash
# Using headless Chrome (if available)
google-chrome --headless --screenshot=dashboard.png \
  --window-size=1200,800 \
  http://localhost:7000/proxy/8787/
```

## GIF/animation
```bash
# Using asciinema (optional)
asciinema rec dashboard.cast \
  -c "watch -n 2 'curl -s http://localhost:7000/proxy/8787/api/status | jq'"
asciinema play dashboard.cast
agg dashboard.cast dashboard.gif  # requires agg (asciinema GIF generator)
```

The text TUI (`python -m skills.dashboard --tui`) already works without
any visual capture tools.
