"""app_test artifacts — dev-useful capture around a GUI test run.

Complements zedarvates/hermes-ai-tester (which makes narrated video reports):
here we collect the deterministic evidence a developer needs for post-mortem —
step results, failure screenshots, tailed crash/logs, and a self-contained HTML
"filmstrip" report. No ffmpeg / GPU (screenshots → HTML, like HyperFrames).
"""

from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Optional

# OculiX/SikuliX prints e.g. "STEP 3 OK: visible welcome.png" / "STEP 2 FAIL: click x.png"
_STEP_RE = re.compile(r"STEP (\d+) (OK|FAIL): (.*)")
_RESULT_RE = re.compile(r"RESULT: (\d+) errors")


def parse_steps(output: str) -> list[dict]:
    steps = []
    for m in _STEP_RE.finditer(output or ""):
        steps.append({"index": int(m.group(1)), "status": m.group(2),
                      "detail": m.group(3).strip()})
    return steps


def collect_logs(paths: list[str], lines: int = 200) -> dict:
    """Tail crash/log files so the report carries the error context."""
    out: dict[str, str] = {}
    for p in paths or []:
        f = Path(p)
        if not f.exists():
            out[p] = "(not found)"
            continue
        try:
            data = f.read_text(encoding="utf-8", errors="replace").splitlines()
            out[p] = "\n".join(data[-lines:])
        except OSError as e:
            out[p] = f"(unreadable: {e})"
    return out


def _img_tags(artifacts_dir: Path) -> list[tuple[str, str]]:
    shots = []
    if artifacts_dir.exists():
        for png in sorted(artifacts_dir.glob("*.png")):
            shots.append((png.name, png.as_uri()))
    return shots


def html_report(name: str, *, output: str, steps: Optional[list] = None,
                logs: Optional[dict] = None, artifacts_dir: Optional[Path] = None,
                out_path: Optional[Path] = None) -> Path:
    """Write a self-contained HTML post-mortem report. Returns its path."""
    steps = steps if steps is not None else parse_steps(output)
    logs = logs or {}
    rm = _RESULT_RE.search(output or "")
    errors = int(rm.group(1)) if rm else (sum(1 for s in steps if s["status"] == "FAIL"))
    verdict = "PASS" if errors == 0 else f"FAIL ({errors})"
    color = "#1a7f37" if errors == 0 else "#cf222e"

    rows = "".join(
        f'<tr class="{s["status"].lower()}"><td>{s["index"]}</td>'
        f'<td>{s["status"]}</td><td>{html.escape(s["detail"])}</td></tr>'
        for s in steps) or '<tr><td colspan="3">(no step markers parsed)</td></tr>'

    shots = _img_tags(artifacts_dir) if artifacts_dir else []
    film = "".join(
        f'<figure><img src="{u}" loading="lazy"><figcaption>{html.escape(n)}</figcaption></figure>'
        for n, u in shots) or "<p>(no screenshots captured)</p>"

    log_blocks = "".join(
        f"<h3>{html.escape(p)}</h3><pre>{html.escape(t)}</pre>" for p, t in logs.items()
    ) or "<p>(no logs collected)</p>"

    doc = f"""<!doctype html><meta charset="utf-8">
<title>app_test report — {html.escape(name)}</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#1f2328}}
 h1 .v{{color:{color}}} table{{border-collapse:collapse;margin:1rem 0}}
 td,th{{border:1px solid #d0d7de;padding:4px 10px}} tr.fail{{background:#ffebe9}}
 tr.ok{{background:#e6ffec}} pre{{background:#0d1117;color:#e6edf3;padding:1rem;
 overflow:auto;border-radius:6px}} .film{{display:flex;gap:1rem;flex-wrap:wrap}}
 figure{{margin:0}} img{{max-width:320px;border:1px solid #d0d7de;border-radius:6px}}
 figcaption{{font-size:12px;color:#656d76}}
</style>
<h1>app_test — {html.escape(name)} · <span class="v">{verdict}</span></h1>
<p>Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · local-first GUI test (OculiX).</p>
<h2>Steps</h2><table><tr><th>#</th><th>status</th><th>detail</th></tr>{rows}</table>
<h2>Screenshots</h2><div class="film">{film}</div>
<h2>Logs / crash</h2>{log_blocks}
<h2>Raw runner output</h2><pre>{html.escape((output or '')[-4000:])}</pre>
"""
    out_path = out_path or Path(f"{name}-report.html")
    out_path.write_text(doc, encoding="utf-8")
    return out_path
