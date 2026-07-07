"""Statusline — compact token savings display for terminal bars.

    python -m skills.statusline [--compact]
"""

from __future__ import annotations

import sys
from pathlib import Path

from skills.statusline.statusline import render, summarize

__all__ = ["render", "summarize", "statusline", "main"]


def statusline(project: str | Path = ".", compact: bool = False) -> str:
    try:
        from skills.metrics import collect
        m = collect(Path(project))
        saved = getattr(m, "tokens_saved", 0) or 0
        always_on = m.always_on_tokens
    except Exception:
        saved = 0
        always_on = 0

    if compact:
        return f"🦶{saved:,}" if saved else "🦶0"
    return f"🦶 {saved:,} tok saved · always-on {always_on:,} tok/session"


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else "."
    compact = "--compact" in sys.argv
    print(statusline(project, compact=compact))


if __name__ == "__main__":
    main()
