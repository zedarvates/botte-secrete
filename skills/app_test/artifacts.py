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
_STEP_RE = re.compile(r"^STEP (\d+) (OK|FAIL): ([^\r\n]*)\r?$", re.MULTILINE)
_RESULT_RE = re.compile(r"^RESULT: (\d+) errors\r?$", re.MULTILINE)


def parse_steps(output: str) -> list[dict]:
    steps = []
    for m in _STEP_RE.finditer(output or ""):
        index = m.group(1)
        step = {"index": int(index) if len(index) <= 12 else None,
                "status": m.group(2), "detail": m.group(3).strip()}
        if len(index) > 12:
            step["index_omitted"] = True
        steps.append(step)
    return steps


def evaluate_run(output: str, *, exit_code: Optional[int] = None,
                 ran: bool = True, steps: Optional[list] = None) -> dict:
    """Combine runner termination and its generated completion marker.

    A zero exit alone does not prove that the generated script completed. The
    script must emit exactly one full-line result, with no reported failures.
    Successful actions need not print STEP markers, so their absence is valid.
    """
    if not ran:
        return {"status": "not_run", "passed": False, "errors": None,
                "reason": "The runner was not started."}
    markers = [match.group(1) for match in _RESULT_RE.finditer(output or "")]
    # Bound integer parsing even when an invalid runner emits an enormous count.
    invalid_count = any(len(count) > 12 for count in markers)
    counts = [int(count) for count in markers if len(count) <= 12]
    failures = max(sum(step["status"] == "FAIL" for step in parse_steps(output)),
                   sum(step["status"] == "FAIL" for step in (steps or [])))
    errors = max(counts + [failures])
    if exit_code is not None and exit_code != 0:
        return {"status": "failed", "passed": False, "errors": errors,
                "reason": f"The runner exited with code {exit_code}."}
    if errors:
        return {"status": "failed", "passed": False, "errors": errors,
                "reason": "The runner reported failed steps or errors."}
    if invalid_count:
        return {"status": "incomplete", "passed": False, "errors": None,
                "reason": "A completion error count exceeds the supported size."}
    if len(counts) != 1:
        reason = ("The generated completion result is missing." if not counts
                  else "Multiple completion results make the run ambiguous.")
        return {"status": "incomplete", "passed": False, "errors": None,
                "reason": reason}
    if exit_code is None:
        return {"status": "incomplete", "passed": False, "errors": 0,
                "reason": "The runner exit code is unavailable."}
    return {"status": "passed", "passed": True, "errors": 0,
            "reason": "The runner exited successfully with one zero-error result."}


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
                out_path: Optional[Path] = None, exit_code: Optional[int] = None,
                ran: bool = True) -> Path:
    """Write a self-contained HTML post-mortem report. Returns its path."""
    steps = steps if steps is not None else parse_steps(output)
    logs = logs or {}
    result = evaluate_run(output, exit_code=exit_code, ran=ran, steps=steps)
    errors = result["errors"]
    verdict = {"passed": "PASS", "failed": "FAIL", "incomplete": "INCOMPLETE",
               "not_run": "NOT RUN"}[result["status"]]
    if result["status"] == "failed" and errors:
        verdict += f" ({errors})"
    color = {"passed": "#1a7f37", "failed": "#cf222e",
             "incomplete": "#9a6700", "not_run": "#656d76"}[result["status"]]

    rows = "".join(
        f'<tr class="{s["status"].lower()}"><td>{s["index"] if s["index"] is not None else "(index omitted)"}</td>'
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
<p>{html.escape(result["reason"])}</p>
<h2>Steps</h2><table><tr><th>#</th><th>status</th><th>detail</th></tr>{rows}</table>
<h2>Screenshots</h2><div class="film">{film}</div>
<h2>Logs / crash</h2>{log_blocks}
<h2>Raw runner output</h2><pre>{html.escape((output or '')[-4000:])}</pre>
"""
    out_path = out_path or Path(f"{name}-report.html")
    out_path.write_text(doc, encoding="utf-8")
    return out_path
