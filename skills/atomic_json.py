"""Small stdlib helpers for durable UTF-8 JSON state files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json(path: str | Path, data: Any, *, indent: int | None = 2) -> None:
    """Atomically replace *path* with a UTF-8 JSON document."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                      dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=indent, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(target)
    except BaseException:
        try:
            Path(temporary).unlink(missing_ok=True)
        finally:
            raise
