"""Report persistence — save any audit as a timestamped, consultable file.

Audits print to the console or return JSON; this turns a report dict into a
self-contained **Markdown and/or HTML** file named `<name>_<YYYY-MM-DD_HHMMSS>`,
written under `.botte/reports/` so every run is browsable at any time.

  save(name, data, fmt="both")   → write report file(s), return paths
  list_reports(dir)              → browse saved reports (name, when, path)

Generic renderer: scalars, lists, list-of-dicts → tables, nested dicts, and ASCII
`diagram` fields as code blocks. Pure stdlib.
"""

from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Optional

DEFAULT_DIR = Path(".botte") / "reports"
_NAME_RE = re.compile(r"^(?P<name>.+)_(?P<stamp>\d{4}-\d{2}-\d{2}_\d{6})\.(md|html)$")


def timestamped_name(name: str, ext: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "report"
    return f"{safe}_{time.strftime('%Y-%m-%d_%H%M%S')}.{ext}"


# ── Markdown rendering ───────────────────────────────────────────────────────

def _is_uniform_dicts(v) -> bool:
    return (isinstance(v, list) and len(v) >= 1 and all(isinstance(i, dict) for i in v)
            and len({frozenset(i.keys()) for i in v}) == 1)


def _md_value(v, depth: int) -> str:
    if isinstance(v, dict):
        return "\n" + _md_dict(v, depth + 1)
    if _is_uniform_dicts(v):
        cols = list(v[0].keys())
        head = "| " + " | ".join(cols) + " |\n| " + " | ".join("---" for _ in cols) + " |"
        rows = "\n".join("| " + " | ".join(str(r.get(c, ""))[:80] for c in cols) + " |"
                         for r in v)
        return "\n" + head + "\n" + rows
    if isinstance(v, list):
        return "\n" + "\n".join(f"- {str(i)[:200]}" for i in v) if v else " _(none)_"
    return f" {v}"


def _md_dict(d: dict, depth: int = 0) -> str:
    out = []
    hashes = "#" * min(depth + 2, 6)
    for k, v in d.items():
        if k == "diagram" and isinstance(v, str):
            out.append(f"{hashes} {k}\n\n```\n{v}\n```")
        elif isinstance(v, (dict, list)):
            out.append(f"{hashes} {k}{_md_value(v, depth)}")
        else:
            out.append(f"- **{k}**: {v}")
    return "\n\n".join(out)


def to_markdown(title: str, data: dict) -> str:
    return (f"# {title}\n\n_Generated {time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"by Botte Secrète._\n\n{_md_dict(data)}\n")


# ── HTML rendering ────────────────────────────────────────────────────────────

def _html_value(v) -> str:
    if isinstance(v, dict):
        return _html_dict(v)
    if _is_uniform_dicts(v):
        cols = list(v[0].keys())
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
        rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, ''))[:160])}</td>"
                                        for c in cols) + "</tr>" for r in v)
        return f"<table><tr>{head}</tr>{rows}</table>"
    if isinstance(v, list):
        return "<ul>" + "".join(f"<li>{html.escape(str(i)[:300])}</li>" for i in v) + "</ul>" if v else "<em>none</em>"
    return html.escape(str(v))


def _html_dict(d: dict, depth: int = 0) -> str:
    parts = []
    for k, v in d.items():
        tag = f"h{min(depth + 2, 5)}"
        if k == "diagram" and isinstance(v, str):
            parts.append(f"<{tag}>{html.escape(k)}</{tag}><pre>{html.escape(v)}</pre>")
        elif isinstance(v, (dict, list)):
            parts.append(f"<{tag}>{html.escape(k)}</{tag}>{_html_value(v)}")
        else:
            parts.append(f"<p><b>{html.escape(k)}:</b> {html.escape(str(v))}</p>")
    return "".join(parts)


def to_html(title: str, data: dict) -> str:
    return f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#1f2328;max-width:60rem}}
table{{border-collapse:collapse;margin:.5rem 0}} td,th{{border:1px solid #d0d7de;padding:4px 10px}}
pre{{background:#0d1117;color:#e6edf3;padding:1rem;border-radius:6px;overflow:auto}}
h2,h3,h4{{border-bottom:1px solid #eaecef;padding-bottom:.2rem}}</style>
<h1>{html.escape(title)}</h1>
<p><em>Generated {time.strftime('%Y-%m-%d %H:%M:%S')} by Botte Secrète.</em></p>
{_html_dict(data)}
"""


# ── save + browse ─────────────────────────────────────────────────────────────

def save(name: str, data: dict, *, fmt: str = "both",
         out_dir: Optional[Path] = None, title: Optional[str] = None) -> list[str]:
    """Write a timestamped report. fmt: md | html | both. Returns the paths."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    title = title or f"{name} report"
    paths = []
    if fmt in ("md", "both"):
        p = out_dir / timestamped_name(name, "md")
        p.write_text(to_markdown(title, data), encoding="utf-8")
        paths.append(str(p))
    if fmt in ("html", "both"):
        p = out_dir / timestamped_name(name, "html")
        p.write_text(to_html(title, data), encoding="utf-8")
        paths.append(str(p))
    return paths


def list_reports(out_dir: Optional[Path] = None) -> list[dict]:
    """List saved reports (most recent first) — consultable at any time."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_DIR
    if not out_dir.exists():
        return []
    rows = []
    for f in out_dir.iterdir():
        m = _NAME_RE.match(f.name)
        if m:
            rows.append({"name": m.group("name"), "when": m.group("stamp"),
                         "fmt": f.suffix.lstrip("."), "path": str(f)})
    return sorted(rows, key=lambda r: r["when"], reverse=True)
