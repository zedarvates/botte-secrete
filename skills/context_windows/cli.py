"""Context Windows — fenêtres indépendantes pour boucles rétroactives.

Au lieu de recharger tout le contexte à chaque itération,
chaque boucle ne charge que :
- la fenêtre active (current step)
- les deltas depuis la dernière étape
- les sections modifiées

Usage:
    python -m skills.context_windows.cli step --active "code review" --deltas 3
    python -m skills.context_windows.cli merge --windows active,history
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextWindow:
    """Une fenêtre de contexte indépendante."""
    id: str
    content: str
    window_type: str  # "active", "history", "reference", "delta"
    step: int = 0
    parent_id: Optional[str] = None
    token_count: int = 0

    def __post_init__(self):
        self.token_count = len(self.content) // 4

    def delta(self, previous: "ContextWindow") -> str:
        """Compute delta from previous version."""
        if self.content == previous.content:
            return "[no change]"
        # Simple line-based diff
        new_lines = set(self.content.split("\n"))
        old_lines = set(previous.content.split("\n"))
        added = new_lines - old_lines
        removed = old_lines - new_lines
        parts = []
        if added:
            parts.append(f"+{len(added)} lines")
        if removed:
            parts.append(f"-{len(removed)} lines")
        return ", ".join(parts) if parts else "[modified]"


class WindowManager:
    """Gère les fenêtres de contexte pour les boucles rétroactives."""

    def __init__(self, max_windows: int = 5):
        self.windows: dict[str, ContextWindow] = {}
        self.max_windows = max_windows
        self.history: list[ContextWindow] = []

    def create_window(self, wid: str, content: str,
                      wtype: str = "active") -> ContextWindow:
        """Create or update a context window."""
        window = ContextWindow(
            id=wid, content=content, window_type=wtype,
            step=len(self.history),
            parent_id=self.history[-1].id if self.history else None,
        )
        self.windows[wid] = window
        self.history.append(window)

        # Éviction LRU
        if len(self.windows) > self.max_windows:
            oldest = min(self.windows.values(), key=lambda w: w.step)
            del self.windows[oldest.id]

        return window

    def get_active(self) -> Optional[ContextWindow]:
        """Get the active window (most recent 'active' type)."""
        active = [w for w in self.windows.values() if w.window_type == "active"]
        return max(active, key=lambda w: w.step) if active else None

    def get_deltas(self, since_step: int = 0) -> list[str]:
        """Get deltas since a given step."""
        deltas = []
        for i in range(since_step, len(self.history)):
            if i == 0:
                continue
            prev = self.history[i - 1]
            curr = self.history[i]
            d = curr.delta(prev)
            if d != "[no change]":
                deltas.append(f"Step {i}: {d}")
        return deltas

    def total_tokens(self) -> int:
        """Total tokens across all windows."""
        return sum(w.token_count for w in self.windows.values())

    def load_for_loop(self, loop_step: int) -> str:
        """Build minimal context for a retroactive loop step."""
        active = self.get_active()
        if not active:
            return ""

        parts = [f"[Active Window] {active.content[:200]}"]

        deltas = self.get_deltas(loop_step)
        if deltas:
            parts.append("[Deltas] " + "; ".join(deltas[-3:]))

        return "\n\n".join(parts)


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="context_windows", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("step", help="Add a context window step")
    s.add_argument("--active", default="", help="Active window content")
    s.add_argument("--deltas", type=int, default=0, help="Steps to show")
    s.set_defaults(func=lambda a: _cmd_step(a, WindowManager()))

    s2 = sub.add_parser("merge", help="Merge windows for loop context")
    s2.add_argument("--windows", default="active", help="Window IDs to merge")
    s2.set_defaults(func=lambda a: print("Merged context for loop"))

    s3 = sub.add_parser("stats", help="Show window stats")
    s3.set_defaults(func=lambda a: _cmd_stats(a, WindowManager()))

    args = p.parse_args(argv)
    return 0


def _cmd_step(args, mgr: WindowManager):
    mgr.create_window("current", args.active, "active")
    context = mgr.load_for_loop(args.deltas)
    print(context)


def _cmd_stats(_args, mgr: WindowManager):
    print(json.dumps({
        "windows": len(mgr.windows),
        "history": len(mgr.history),
        "total_tokens": mgr.total_tokens(),
    }, indent=2))


if __name__ == "__main__":
    main()
