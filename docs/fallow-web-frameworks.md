# Fallow-like web framework patterns

Extending `fallow_like` taint analysis to web frameworks:

## Flask patterns
- `@app.route(..., methods=['POST'])` → entry point
- `request.form.get(...)` → user input (taint source)
- `render_template(..., data=...)` → XSS sink
- `redirect(request.args.get('next'))` → open redirect

## FastAPI patterns
- `@app.post("/...")` → entry point
- `Query(...)`, `Body(...)`, `Form(...)` → user input
- `Response(content=...)` → response sink
- `BackgroundTasks.add_task(...)` → background execution

## Express patterns (JS)
- `app.post('/...', (req, res) => ...)` → entry point
- `req.body`, `req.query`, `req.params` → user input
- `res.send(...)` → XSS sink
- `child_process.exec(req.body.cmd)` → command injection

## Implementation
Add to `skills/fallow_like/analyzers/taint.py`:
- `TAINT_SOURCES`: extend with `request.form`, `Query()`, `req.body`
- `TAINT_SINKS`: extend with `render_template`, `Response()`, `res.send`
- Framework detection: check imports (`from flask import`, `from fastapi import`)
