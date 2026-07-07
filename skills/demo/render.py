"""ANSI panel renderer — side-by-side boxes for the demo TUI.

Pure stdlib box-drawing. No colour library dependency: a tiny ANSI-code table
is enough, and it degrades gracefully (plain text) when NO_COLOR is set or
output isn't a TTY.
"""

from __future__ import annotations

import os
import re
import sys

_CODES = {"reset": "\x1b[0m", "bold": "\x1b[1m", "dim": "\x1b[2m",
          "green": "\x1b[32m", "yellow": "\x1b[33m", "red": "\x1b[31m",
          "cyan": "\x1b[36m", "magenta": "\x1b[35m"}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def c(text: str, *styles: str) -> str:
    if not styles or not _color_enabled():
        return text
    prefix = "".join(_CODES.get(s, "") for s in styles)
    return f"{prefix}{text}{_CODES['reset']}"


class Panel:
    def __init__(self, title: str, lines: list[str], width: int = 34):
        self.title = title
        self.lines = lines
        self.width = width

    def render(self) -> list[str]:
        w = self.width
        # visible-title length may include ANSI codes; measure the raw text instead
        raw_title_len = len(_strip_ansi(self.title))
        dashes = max(0, w - 3 - raw_title_len)
        top = ("┌─ " + self.title + " " + "─" * dashes + "┐")
        body = []
        for line in self.lines[: max(1, w // 6)]:
            visible = _strip_ansi(line)
            if len(visible) > w - 1:
                # trim the raw text, not the ANSI-wrapped one — keeps codes intact
                line = visible[: w - 4] + "..."
                visible = line
            pad = " " * max(0, (w - 1) - len(visible))
            body.append("│ " + line + pad + "│")
        if not self.lines:
            body.append("│ " + "(none yet)".ljust(w - 1) + "│")
        bottom = "└" + "─" * w + "┘"
        return [top] + body + [bottom]


def render_grid(panels: list[Panel], cols: int = 2) -> str:
    """Lay panels out `cols` per row, padding rows to equal height."""
    out_lines: list[str] = []
    for row_start in range(0, len(panels), cols):
        row = panels[row_start: row_start + cols]
        rendered = [p.render() for p in row]
        height = max(len(r) for r in rendered)
        for i, (p, r) in enumerate(zip(row, rendered)):
            filler = " " * (p.width + 2)
            rendered[i] = r + [filler] * (height - len(r))
        for i in range(height):
            out_lines.append("  ".join(r[i] for r in rendered))
        out_lines.append("")
    return "\n".join(out_lines)


def clear_screen() -> None:
    if _color_enabled():
        print("\x1b[2J\x1b[H", end="")
