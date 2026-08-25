"""Events — the unified decision log every showcase feature reads from.

One append-only JSONL file per project (`.botte/events.jsonl`). Every filter in
the belt (micro-NN, deterministic, local LLM, cloud) that makes a routing,
caching, or escalation decision can log one line here — 0 tokens, 0 network,
pure stdlib. Demo mode, the live dashboard, and session replay all read this
same file instead of poking each skill's own storage.

    log_event("route", filter=1, nn="effort_classifier", out="local", ...)
    read_events(project_root)               # all events, oldest first
    tail_events(project_root, n=20)          # last N events

Rotation: once the file exceeds MAX_BYTES, it's truncated to the last
KEEP_FRACTION of its lines — same "keep it small, keep it local" spirit as
`.botte-cache/`. Never raises: a logging failure must never break the caller.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator, Optional

MAX_BYTES = 5 * 1024 * 1024   # rotate past 5 MB
KEEP_FRACTION = 0.5            # keep the newest half on rotation

KNOWN_KINDS = {"route", "cache", "escalate", "nn_out", "fusion",
               "loop_start", "loop_decision", "loop_stop", "loop_saving",
               "qa_outcome", "qa_trajectory", "qa_shadow_advice"}


def _events_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".botte" / "events.jsonl"


def log_event(kind: str, project_root: str | Path = ".", **fields) -> None:
    """Append one decision event (best-effort, never raises).

    `kind` is a free-form label (e.g. "route", "cache", "escalate", "nn_out")
    — see KNOWN_KINDS for the ones the showcase tools recognise by default.
    """
    try:
        p = _events_path(project_root)
        rec = {"ts": time.time(), "kind": kind, **fields}
        p.parent.mkdir(parents=True, exist_ok=True)
        _maybe_rotate(p)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass


def _maybe_rotate(p: Path) -> None:
    try:
        if not p.exists() or p.stat().st_size < MAX_BYTES:
            return
        lines = p.read_text(encoding="utf-8").splitlines()
        keep = lines[-int(len(lines) * KEEP_FRACTION):] if lines else []
        p.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    except OSError:
        pass


def read_events(project_root: str | Path = ".", limit: Optional[int] = None) -> list[dict]:
    """All events, oldest first. `limit` keeps only the newest N."""
    p = _events_path(project_root)
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out[-limit:] if limit else out


def tail_events(project_root: str | Path = ".", n: int = 20) -> list[dict]:
    return read_events(project_root, limit=n)


def follow_events(project_root: str | Path = ".", *, poll_interval: float = 0.5
                   ) -> Iterator[dict]:
    """Yield new events as they're appended (blocking generator, for `--live`)."""
    p = _events_path(project_root)
    seen = len(read_events(project_root))
    while True:
        recs = read_events(project_root)
        if len(recs) < seen:
            # Rotation replaced the file with a shorter tail. Treat its current
            # contents as the new baseline instead of waiting for the old line
            # count to be reached again.
            seen = 0
        for rec in recs[seen:]:
            yield rec
        seen = len(recs)
        time.sleep(poll_interval)


def clear_events(project_root: str | Path = ".") -> None:
    p = _events_path(project_root)
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
