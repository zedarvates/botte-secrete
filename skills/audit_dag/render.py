"""Renderers — derive the two views from one canonical AuditDAG.

  to_compact  → machine-first, token-minimal, lossless, every node addressable by id.
                This is the form an LLM consumes (it is told to walk ORDER n1..nN).
  to_html     → the same graph, styled for humans.

One source of truth, two renderings — the HTML is never authored separately, so the
two can't drift.
"""

from __future__ import annotations

import html

from skills.audit_dag.dag import AuditDAG

_SEV_ORDER = ["critical", "error", "warning", "info"]
_SEV_COLOR = {"critical": "#b00020", "error": "#d35400", "warning": "#b8860b", "info": "#3b6ea5"}
_GRADE_COLOR = {"A": "#2e7d32", "B": "#689f38", "C": "#b8860b", "D": "#d35400", "F": "#b00020"}


def to_compact(dag: AuditDAG) -> str:
    """Token-minimal, addressable, lossless rendering for an LLM."""
    head = f"AUDIT grade={dag.grade} n={len(dag.nodes)} " + " ".join(
        f"{k}={dag.counts[k]}" for k in _SEV_ORDER if k in dag.counts)
    lines = [head.rstrip(), "# address every node by id; none may be skipped.",
             "ORDER " + " ".join(dag.order)]
    for n in dag.nodes:
        loc = f"{n.file}:{n.line}" if n.file else "-"
        cnt = f" x{n.count}" if n.count > 1 else ""
        fix = f' >fix "{n.fix}"' if n.fix else ""
        lines.append(f'{n.id} {n.severity} {n.rule} {loc}{cnt} "{n.message}"{fix}')
    if dag.edges:
        lines.append("EDGES " + " ".join(f"{e.src}-{e.kind}-{e.dst}" for e in dag.edges))
    return "\n".join(lines)


def to_html(dag: AuditDAG, *, title: str = "Botte Secrète — Audit") -> str:
    """Human HTML rendered from the same DAG."""
    g = dag.grade
    gcol = _GRADE_COLOR.get(g, "#555")
    chips = " ".join(
        f'<span class="chip" style="background:{_SEV_COLOR[k]}">{k} {dag.counts[k]}</span>'
        for k in _SEV_ORDER if k in dag.counts)

    rows = []
    for n in dag.nodes:
        loc = f"{html.escape(n.file)}:{n.line}" if n.file else "—"
        cnt = f' <span class="count">×{n.count}</span>' if n.count > 1 else ""
        fix = f'<div class="fix">↳ {html.escape(n.fix)}</div>' if n.fix else ""
        rows.append(
            f'<tr class="sev-{n.severity}"><td class="id">{n.id}</td>'
            f'<td><span class="sev" style="background:{_SEV_COLOR[n.severity]}">'
            f'{n.severity}</span></td><td class="rule">{html.escape(n.rule)}</td>'
            f'<td class="loc">{loc}</td><td>{html.escape(n.message)}{cnt}{fix}</td></tr>')

    edges = ""
    if dag.edges:
        items = " ".join(f'<code>{e.src}→{e.dst}</code> <small>({e.kind})</small>'
                         for e in dag.edges)
        edges = f'<section class="edges"><h2>Relations</h2><p>{items}</p></section>'

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
 body{{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f7f7f8;color:#1a1a1a}}
 header{{padding:24px 28px;background:#fff;border-bottom:1px solid #e5e5e5;display:flex;
  align-items:center;gap:18px}}
 .grade{{font-size:34px;font-weight:800;color:#fff;background:{gcol};width:58px;height:58px;
  border-radius:12px;display:flex;align-items:center;justify-content:center}}
 h1{{font-size:18px;margin:0}} .chip,.sev{{color:#fff;border-radius:999px;padding:2px 10px;
  font-size:12px;font-weight:600}} .chips{{margin-top:6px}}
 main{{padding:20px 28px}} table{{width:100%;border-collapse:collapse;background:#fff;
  border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
 th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top}}
 th{{background:#fafafa;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#666}}
 .id{{font-family:ui-monospace,monospace;color:#888}} .rule{{font-weight:600}}
 .loc{{font-family:ui-monospace,monospace;font-size:13px;color:#3b6ea5;white-space:nowrap}}
 .fix{{color:#2e7d32;font-size:13px;margin-top:4px}} .count{{color:#b00020;font-weight:700}}
 .edges{{margin-top:18px;color:#555}} .edges code{{background:#eee;padding:1px 5px;border-radius:4px}}
 footer{{padding:14px 28px;color:#999;font-size:12px}}
</style></head><body>
<header><div class="grade">{g}</div><div><h1>{html.escape(title)}</h1>
 <div class="chips">{chips or '<span class="chip" style="background:#2e7d32">clean</span>'}</div></div></header>
<main><table><thead><tr><th>#</th><th>Sev</th><th>Rule</th><th>Location</th><th>Finding</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=5>No findings 🎉</td></tr>'}</tbody></table>
{edges}</main>
<footer>Rendered from one canonical audit DAG ({len(dag.nodes)} nodes, {len(dag.edges)} edges) — machine + human views can't drift.</footer>
</body></html>"""
