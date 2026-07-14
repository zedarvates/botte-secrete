"""Append-only local ledger for measured loop outcomes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

from skills.loop_optimizer.models import LoopOutcome


DEFAULT_LEDGER = Path.home() / ".botte" / "loop-ledger.jsonl"


class LoopLedger:
    def __init__(self, path: str | Path = DEFAULT_LEDGER):
        self.path = Path(path)

    def append(self, outcome: LoopOutcome | dict[str, Any]) -> dict[str, Any]:
        record = outcome.to_dict() if isinstance(outcome, LoopOutcome) else dict(outcome)
        if not str(record.get("loop_id", "")).strip():
            raise ValueError("ledger record requires loop_id")
        record.setdefault("ts", time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record

    def read(self, loop_id: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return records
        for line in lines:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(record, dict) and (loop_id is None or record.get("loop_id") == loop_id):
                records.append(record)
        return records

    @staticmethod
    def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        items = list(records)
        return {
            "iterations": len(items),
            "tokens_total": sum(int(item.get("total_tokens", 0)) for item in items),
            "context_tokens": sum(int(item.get("context_tokens", 0)) for item in items),
            "execution_tokens": sum(int(item.get("execution_tokens", 0)) for item in items),
            "verification_tokens": sum(int(item.get("verification_tokens", 0)) for item in items),
            "cloud_tokens": sum(int(item.get("cloud_tokens", 0)) for item in items),
            "cache_hits": sum(bool(item.get("cache_hit")) for item in items),
            "success": bool(items and items[-1].get("success")),
        }
