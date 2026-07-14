"""Persistent, risk-aware verification selection for loop deltas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skills.atomic_json import write_json


STORE = Path.home() / ".botte" / "harness-delta.json"


class DeltaVerifier:
    def __init__(self, store_path: str | Path | None = STORE):
        self.store_path = Path(store_path) if store_path is not None else None
        self.snapshots: dict[str, str] = {}
        self.risk_scores: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if self.store_path is None or not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.snapshots = dict(data.get("snapshots", {}))
            self.risk_scores = {key: float(value) for key, value in data.get("risk_scores", {}).items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.snapshots, self.risk_scores = {}, {}

    def _save(self) -> None:
        if self.store_path is not None:
            write_json(self.store_path, {"snapshots": self.snapshots,
                                         "risk_scores": self.risk_scores})

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def snapshot(self, section: str, content: str) -> None:
        self.snapshots[section] = self._hash(content)
        self._save()

    def has_changed(self, section: str, content: str) -> bool:
        previous = self.snapshots.get(section)
        return previous is None or previous != self._hash(content)

    def set_risk(self, section: str, score: float) -> None:
        self.risk_scores[section] = max(0.0, min(1.0, float(score)))
        self._save()

    def needs_verification(self, section: str, content: str,
                           risk_threshold: float = 0.3) -> tuple[bool, str]:
        if self.has_changed(section, content):
            return True, "section modified"
        risk = self.risk_scores.get(section, 0.0)
        if risk >= risk_threshold:
            return True, f"risk score {risk:.2f} >= {risk_threshold}"
        return False, "unchanged + low risk"

    def sections_to_verify(self, sections: dict[str, str], *, final: bool = False,
                           risk_threshold: float = 0.3) -> list[dict[str, str]]:
        if final:
            return [{"section": section, "reason": "final verification"}
                    for section in sections]
        return [{"section": section, "reason": reason}
                for section, content in sections.items()
                for needed, reason in [self.needs_verification(section, content, risk_threshold)]
                if needed]
