"""Persistent context windows and ordered structured deltas."""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from skills.atomic_json import write_json


STORE = Path.home() / ".botte" / "context-windows.json"


@dataclass
class ContextWindow:
    id: str
    content: str
    window_type: str
    step: int = 0
    parent_id: Optional[str] = None
    token_count: int = 0

    def __post_init__(self) -> None:
        self.token_count = len(self.content) // 4


@dataclass(frozen=True)
class WindowDelta:
    window_id: str
    from_step: int
    to_step: int
    opcodes: tuple[tuple[str, int, int, int, int], ...]

    @property
    def changed_lines(self) -> int:
        return sum(
            max(i2 - i1, j2 - j1)
            for tag, i1, i2, j1, j2 in self.opcodes if tag != "equal"
        )

    def to_dict(self) -> dict:
        return {
            "window_id": self.window_id,
            "from_step": self.from_step,
            "to_step": self.to_step,
            "opcodes": [list(opcode) for opcode in self.opcodes],
            "changed_lines": self.changed_lines,
        }


class WindowManager:
    def __init__(self, max_windows: int = 5, store_path: str | Path | None = STORE):
        self.windows: dict[str, ContextWindow] = {}
        self.max_windows = max_windows
        self.history: list[ContextWindow] = []
        self.store_path = Path(store_path) if store_path is not None else None
        self._load()

    def _load(self) -> None:
        if self.store_path is None or not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.max_windows = int(data.get("max_windows", self.max_windows))
            self.history = [ContextWindow(**item) for item in data.get("history", [])]
            self.windows = {item["id"]: ContextWindow(**item)
                            for item in data.get("windows", [])}
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.windows = {}
            self.history = []

    def _save(self) -> None:
        if self.store_path is not None:
            write_json(self.store_path, {
                "max_windows": self.max_windows,
                "windows": [asdict(window) for window in self.windows.values()],
                "history": [asdict(window) for window in self.history[-100:]],
            })

    def create_window(self, wid: str, content: str, wtype: str = "active") -> ContextWindow:
        window = ContextWindow(wid, content, wtype, len(self.history),
                               self.history[-1].id if self.history else None)
        self.windows[wid] = window
        self.history.append(window)
        if len(self.windows) > self.max_windows:
            oldest = min(self.windows.values(), key=lambda item: item.step)
            del self.windows[oldest.id]
        self._save()
        return window

    def merge(self, window_ids: list[str]) -> str:
        return "\n\n".join(self.windows[wid].content for wid in window_ids if wid in self.windows)

    def get_active(self) -> Optional[ContextWindow]:
        active = [item for item in self.windows.values() if item.window_type == "active"]
        return max(active, key=lambda item: item.step) if active else None

    def structured_deltas(self, since_step: int = 0) -> list[WindowDelta]:
        deltas: list[WindowDelta] = []
        for index in range(max(1, since_step), len(self.history)):
            previous, current = self.history[index - 1], self.history[index]
            matcher = difflib.SequenceMatcher(
                None, previous.content.splitlines(), current.content.splitlines(), autojunk=False)
            opcodes = tuple(tuple(opcode) for opcode in matcher.get_opcodes() if opcode[0] != "equal")
            if opcodes:
                deltas.append(WindowDelta(current.id, previous.step, current.step, opcodes))
        return deltas

    def get_deltas(self, since_step: int = 0) -> list[str]:
        return [f"Step {item.to_step}: {item.window_id} changed {item.changed_lines} line(s)"
                for item in self.structured_deltas(since_step)]

    def total_tokens(self) -> int:
        return sum(item.token_count for item in self.windows.values())

    def load_for_loop(self, loop_step: int) -> str:
        active = self.get_active()
        if active is None:
            return ""
        parts = [f"[Active Window] {active.content[:200]}"]
        deltas = self.get_deltas(loop_step)
        if deltas:
            parts.append("[Deltas] " + "; ".join(deltas[-3:]))
        return "\n\n".join(parts)
