"""Docs lifecycle — keep plans/TODOs/reports from becoming token waste.

Finished work shouldn't keep costing tokens. Two jobs, both **confirm-gated**
(preview by default, act only with an explicit write):

  tasks    find finished tasks in plan/TODO markdown (checkbox lists) so an LLM
           stops re-reading done items as "to do"; prune them (preserving the
           removed items in an archive file) or archive a fully-done plan.
  reports  keep the N most recent of each `.botte` report, archive the rest, so
           the reports directory doesn't balloon over time.

Pure stdlib, 0 cloud tokens.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from skills.docs_steward.steward import _est_tokens

try:
    from skills.fallow_like.scanner import DEFAULT_IGNORE_DIRS
except Exception:
    DEFAULT_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
                           "dist", "build", ".botte", ".pytest_cache"}

_CHECKBOX_DONE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+")
_CHECKBOX_OPEN = re.compile(r"^\s*[-*]\s+\[ \]\s+")
ARCHIVE_DIRNAME = ".botte/archive"

# Only *dedicated* plan/todo files are prune/archive targets — a README or doc
# that merely contains a checklist (e.g. a checked-off roadmap) is left alone.
_PLAN_STEMS = {"todo", "todos", "plan", "plans", "task", "tasks", "roadmap", "backlog"}
_PLAN_PREFIXES = ("plan", "todo", "tasks", "task", "roadmap", "backlog")
_PLAN_DIRS = {"plans", "plan", "tasks", "task", "todo", "todos", "backlog"}


@dataclass
class TaskFile:
    path: str
    open_tasks: int
    done_tasks: int
    done_tokens: int   # tokens of the done checkbox lines — the waste
    fully_done: bool
    is_plan: bool      # a dedicated plan/todo file → safe to prune/archive

    def to_dict(self) -> dict:
        return asdict(self)


def _rel(root: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return p.name


def _is_plan_file(root: Path, p: Path) -> bool:
    stem = p.stem.lower()
    if stem in _PLAN_STEMS or stem.startswith(_PLAN_PREFIXES):
        return True
    try:
        parent_parts = {x.lower() for x in p.resolve().relative_to(root).parts[:-1]}
    except ValueError:
        parent_parts = set()
    return bool(parent_parts & _PLAN_DIRS)


def scan_tasks(root: str | Path) -> list:
    """Markdown files holding checkbox tasks, with open/done counts + waste."""
    import os
    root = Path(root).resolve()
    out: list = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS]
        for fn in filenames:
            if not fn.lower().endswith((".md", ".mdx", ".markdown")):
                continue
            p = Path(dirpath) / fn
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            done = [ln for ln in lines if _CHECKBOX_DONE.match(ln)]
            opened = [ln for ln in lines if _CHECKBOX_OPEN.match(ln)]
            if not done and not opened:
                continue
            out.append(TaskFile(
                path=_rel(root, p), open_tasks=len(opened), done_tasks=len(done),
                done_tokens=_est_tokens(sum(len(ln) for ln in done)),
                fully_done=bool(done) and not opened,
                is_plan=_is_plan_file(root, p)))
    out.sort(key=lambda t: t.path)
    return out


def prune_tasks(path: str | Path, root: str | Path, *, dry_run: bool = True) -> dict:
    """Strip done items (preserving them in an archive file), or archive a
    fully-done plan. Confirm-gated: dry_run=True changes nothing."""
    root = Path(root).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    archive = root / ARCHIVE_DIRNAME
    rel = _rel(root, p)
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"path": rel, "action": "error", "removed": 0}

    done = [ln for ln in lines if _CHECKBOX_DONE.match(ln)]
    opened = [ln for ln in lines if _CHECKBOX_OPEN.match(ln)]
    if not done:
        return {"path": rel, "action": "none", "removed": 0}

    # fully done → archive the whole file
    if not opened:
        target = archive / p.name
        if not dry_run:
            archive.mkdir(parents=True, exist_ok=True)
            p.replace(target)
        return {"path": rel, "action": "archive_file", "removed": len(done),
                "archived_to": _rel(root, target)}

    # mixed → keep open items, move done items to an archive file
    kept = [ln for ln in lines if not _CHECKBOX_DONE.match(ln)]
    afile = archive / (p.stem + ".done.md")
    if not dry_run:
        archive.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with afile.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## archived from {rel} @ {stamp}\n" + "\n".join(done) + "\n")
        p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return {"path": rel, "action": "pruned", "removed": len(done),
            "archived_to": _rel(root, afile)}


def prune_all(root: str | Path, *, dry_run: bool = True) -> list:
    """Prune every *plan* file that has done items. Confirm-gated.

    Only dedicated plan/todo files are touched — docs that merely contain a
    checklist (a README roadmap, say) are never pruned.
    """
    root = Path(root).resolve()
    results = []
    for tf in scan_tasks(root):
        if tf.done_tasks and tf.is_plan:
            results.append(prune_tasks(tf.path, root, dry_run=dry_run))
    return results


def report_hygiene(root: str | Path, keep: int = 5) -> dict:
    """Group `.botte` reports by name; keep the N most recent, list the rest."""
    from skills.report import list_reports
    root = Path(root).resolve()
    reports_dir = root / ".botte" / "reports"
    rows = list_reports(reports_dir)
    by_name: dict = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r)
    keep_list, archive_list = [], []
    for name, items in by_name.items():
        items.sort(key=lambda r: r["when"], reverse=True)
        keep_list.extend(items[:keep])
        archive_list.extend(items[keep:])
    return {"keep": keep_list, "archive": archive_list,
            "names": len(by_name), "total": len(rows)}


def archive_reports(root: str | Path, keep: int = 5, *, dry_run: bool = True) -> list:
    """Move older reports into `.botte/reports/archive/`. Confirm-gated."""
    root = Path(root).resolve()
    dest = root / ".botte" / "reports" / "archive"
    hy = report_hygiene(root, keep)
    moved = []
    for r in hy["archive"]:
        src = Path(r["path"])
        target = dest / src.name
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
            src.replace(target)
        moved.append({"name": r["name"], "when": r["when"],
                      "to": _rel(root, target), "moved": not dry_run})
    return moved


def lifecycle_report(root: str | Path, keep: int = 5) -> dict:
    """Combined tasks + reports lifecycle summary for /checkup or the CLI."""
    tasks = scan_tasks(root)
    hy = report_hygiene(root, keep)
    return {
        "tasks": {
            "files": [t.to_dict() for t in tasks],
            "open_total": sum(t.open_tasks for t in tasks),
            "done_total": sum(t.done_tasks for t in tasks),
            "done_token_waste": sum(t.done_tokens for t in tasks if t.is_plan),
            "fully_done_files": [t.path for t in tasks if t.fully_done and t.is_plan],
        },
        "reports": {
            "total": hy["total"], "names": hy["names"],
            "keep": len(hy["keep"]), "to_archive": len(hy["archive"]),
            "keep_per_name": keep,
        },
    }
