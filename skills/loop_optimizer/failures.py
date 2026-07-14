"""Persistent bounded memory of failed loop actions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from skills.atomic_json import write_json


DEFAULT_FAILURES = Path.home() / ".botte" / "loop-failures.json"
MAX_FAILURES = 500


def normalize_message(message: str) -> str:
    """Normalize formatting noise while preserving the error's semantics."""
    return re.sub(r"\s+", " ", message.strip().lower())[:500]


def failure_signature(error_type: str, message: str, fingerprints: dict[str, str],
                      action: str) -> str:
    material = json.dumps({
        "error_type": error_type.strip().lower(),
        "message": normalize_message(message),
        "fingerprints": sorted(fingerprints.items()),
        "action": action.strip().lower(),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class FailureMemory:
    def __init__(self, path: str | Path = DEFAULT_FAILURES, max_entries: int = MAX_FAILURES):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.path = Path(path)
        self.max_entries = max_entries
        self.records = self._load()

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []
        return [item for item in data if isinstance(item, dict)][-self.max_entries:]

    def record(self, *, error_type: str, message: str,
               fingerprints: dict[str, str], action: str,
               loop_id: str = "") -> str:
        signature = failure_signature(error_type, message, fingerprints, action)
        self.records.append({
            "signature": signature,
            "loop_id": loop_id,
            "action": action,
            "ts": time.time(),
        })
        self.records = self.records[-self.max_entries:]
        write_json(self.path, self.records)
        return signature

    def count(self, signature: str, *, loop_id: str | None = None) -> int:
        return sum(
            item.get("signature") == signature
            and (loop_id is None or item.get("loop_id") == loop_id)
            for item in self.records
        )

    def repeated(self, signature: str, *, loop_id: str | None = None,
                 threshold: int = 2) -> bool:
        if threshold < 1:
            raise ValueError("threshold must be positive")
        return self.count(signature, loop_id=loop_id) >= threshold
