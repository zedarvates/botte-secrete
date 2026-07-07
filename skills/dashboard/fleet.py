"""Fleet view — aggregate the dashboard picture across every project on this
machine that's opted in, instead of one repo at a time.

Explicit opt-in by design: this reads a machine-wide registry
(`~/.botte/fleet.json`) of project paths the user has *registered*, not a
filesystem scan — no surprise about which directories get touched. A natural
place to auto-register is `bootstrap` (deploying botte into a project), but
that wiring is left for later; `fleet add` covers it today.

    add(path)            register a project
    remove(path)          drop it
    list_fleet()          registered paths
    aggregate()            collect() every registered project, sum totals
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_FLEET_PATH = Path.home() / ".botte" / "fleet.json"


def _load(path: Optional[Path] = None) -> list[str]:
    p = path or DEFAULT_FLEET_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(dict.fromkeys(data.get("projects", [])))  # de-dup, keep order
    except (OSError, json.JSONDecodeError):
        return []


def _save(projects: list[str], path: Optional[Path] = None) -> None:
    p = path or DEFAULT_FLEET_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"projects": projects}, indent=2), encoding="utf-8")


def add(project: str | Path, path: Optional[Path] = None) -> list[str]:
    resolved = str(Path(project).resolve())
    projects = _load(path)
    if resolved not in projects:
        projects.append(resolved)
        _save(projects, path)
    return projects


def remove(project: str | Path, path: Optional[Path] = None) -> list[str]:
    resolved = str(Path(project).resolve())
    projects = [p for p in _load(path) if p != resolved]
    _save(projects, path)
    return projects


def list_fleet(path: Optional[Path] = None) -> list[str]:
    return _load(path)


def aggregate(path: Optional[Path] = None) -> dict:
    """collect() every registered project; projects that error/vanished are
    reported separately instead of silently dropped or breaking the whole view."""
    from skills.dashboard.dashboard import collect

    projects = _load(path)
    ok: list[dict] = []
    errored: list[dict] = []

    for proj in projects:
        try:
            if not Path(proj).is_dir():
                raise FileNotFoundError(f"{proj} no longer exists")
            data = collect(proj)
        except Exception as e:
            errored.append({"project": proj, "error": str(e)})
            continue
        rs = data.get("routing_savings", {}) or {}
        fixes = data.get("outstanding_fixes", {}) or {}
        m = data.get("metrics", {}) or {}
        ok.append({
            "project": proj,
            "loc": m.get("loc_total", 0) if isinstance(m.get("loc_total"), int) else 0,
            "tokens_saved": rs.get("tokens_saved_total", 0) or 0,
            "outstanding_fixes": fixes.get("total", 0) or 0,
        })

    totals = {
        "projects_ok": len(ok),
        "projects_errored": len(errored),
        "loc_total": sum(p["loc"] for p in ok),
        "tokens_saved_total": sum(p["tokens_saved"] for p in ok),
        "outstanding_fixes_total": sum(p["outstanding_fixes"] for p in ok),
    }
    return {"projects": ok, "errored": errored, "totals": totals}
