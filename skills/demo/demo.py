"""Demo mode — render the belt's decisions as they happen.

Two sources feed the same panels:
  --scripted   the built-in scenario (scenario.py) — works on a bare machine,
               no local LLM, no network. This is the README-GIF / salon-demo mode.
  --live       tails a real project's `.botte/events.jsonl` (skills.events)
               while an agent works, so the panels show genuine decisions.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, Iterator

from skills.demo.render import Panel, render_grid, clear_screen, c
from skills.demo import scenario as _scenario


def _routing_lines(events: list[dict]) -> list[str]:
    lines = []
    for e in reversed(events):
        if e.get("kind") != "route":
            continue
        out = e.get("out", "?")
        tag = c("LOCAL", "green") if out == "local" else c("CLOUD", "yellow")
        lines.append(f"{tag}  {str(e.get('task') or e.get('reason', ''))[:40]}")
    return lines[:6]


def _savings_lines(events: list[dict]) -> list[str]:
    saved = sum(int(e.get("tokens_saved", 0)) for e in events)
    cloud = sum(1 for e in events if e.get("kind") == "route" and e.get("out") == "cloud")
    cache_hits = sum(1 for e in events if e.get("kind") == "cache" and e.get("hit"))
    avoided = sum(1 for e in events if e.get("kind") == "route" and e.get("out") == "local")
    return [
        f"tokens saved      {saved:>8}",
        f"cloud calls made  {cloud:>8}",
        f"cloud calls saved {avoided:>8}",
        f"cache hits        {cache_hits:>8}",
    ]


def _nn_lines(events: list[dict]) -> list[str]:
    lines = []
    for e in reversed(events):
        if e.get("kind") != "nn_out":
            continue
        model = e.get("model", "?")
        probs = e.get("probs")
        label = e.get("label", "")
        probs_s = "[" + "|".join(f"{p:.2f}" for p in probs) + "]" if probs else ""
        lines.append(f"{model:<18} {probs_s} {label}")
    for e in reversed(events):
        if e.get("kind") == "route" and e.get("nn") and e.get("nn") != "-":
            lines.append(f"{e['nn']:<18} conf={e.get('conf', '?')}")
    return lines[:6]


def _escalation_lines(events: list[dict]) -> list[str]:
    lines = []
    for e in reversed(events):
        if e.get("kind") != "escalate":
            continue
        frm, to = e.get("from", "?"), e.get("to", "?")
        lines.append(f"{frm} → {to}  {str(e.get('reason', ''))[:28]}")
    return lines[:6]


def build_panels(events: list[dict]) -> list[Panel]:
    return [
        Panel(c("ROUTING", "bold", "cyan"), _routing_lines(events)),
        Panel(c("SAVINGS (session)", "bold", "green"), _savings_lines(events)),
        Panel(c("MICRO-NN", "bold", "magenta"), _nn_lines(events)),
        Panel(c("ESCALATIONS", "bold", "red"), _escalation_lines(events)),
    ]


def run_scripted(*, delay: float = 0.6, clear: bool = True) -> Iterator[str]:
    """Yield one rendered frame per step of the built-in scenario."""
    seen: list[dict] = []
    for step in _scenario.STEPS:
        seen.append(step)
        frame = render_grid(build_panels(seen))
        if clear:
            clear_screen()
        yield frame
        if delay:
            time.sleep(delay)


def run_live(project_root: str | Path = ".", *, poll_interval: float = 0.5,
             clear: bool = True) -> Iterator[str]:
    """Yield a refreshed frame every time a new real event lands."""
    from skills.events import read_events, follow_events
    seen = list(read_events(project_root))
    frame = render_grid(build_panels(seen))
    if clear:
        clear_screen()
    yield frame
    for rec in follow_events(project_root, poll_interval=poll_interval):
        seen.append(rec)
        frame = render_grid(build_panels(seen))
        if clear:
            clear_screen()
        yield frame


def run_replay(events: list[dict], *, delay: float = 0.3, clear: bool = True
               ) -> Iterator[str]:
    """Replay a captured event list (e.g. from `events tail --json`)."""
    seen: list[dict] = []
    for rec in events:
        seen.append(rec)
        frame = render_grid(build_panels(seen))
        if clear:
            clear_screen()
        yield frame
        if delay:
            time.sleep(delay)
