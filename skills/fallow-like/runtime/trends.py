"""Trend tracking and alerting."""

from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel
from datetime import datetime
import json
import sqlite3


class TrendPoint(BaseModel):
    timestamp: str
    score: int
    findings_count: int
    new_findings: int = 0
    resolved_findings: int = 0


class Alert(BaseModel):
    rule_id: str
    severity: str
    message: str
    metric: str
    threshold: float
    current_value: float


class TrendTracker:
    def __init__(self, db_path: Path = Path(".fallow-history.db")):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    findings_count INTEGER NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0
                )
            """)

    def save_snapshot(self, score: int, findings_count: int, data: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO snapshots (timestamp, score, findings_count, data) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), score, findings_count, json.dumps(data)),
            )

    def get_trends(self, limit: int = 30) -> list[TrendPoint]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT timestamp, score, findings_count FROM snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        points: list[TrendPoint] = []
        prev_count = 0
        for ts, score, count in reversed(rows):
            points.append(TrendPoint(
                timestamp=ts,
                score=score,
                findings_count=count,
                new_findings=max(0, count - prev_count),
                resolved_findings=max(0, prev_count - count),
            ))
            prev_count = count

        return list(reversed(points))

    def check_alerts(self, current_score: int, current_findings: int) -> list[Alert]:
        alerts: list[Alert] = []

        if current_score < 50:
            alerts.append(Alert(
                rule_id="ALERT001", severity="critical",
                message=f"Health score dropped to {current_score}/100",
                metric="score", threshold=50, current_value=current_score,
            ))
        elif current_score < 70:
            alerts.append(Alert(
                rule_id="ALERT002", severity="warning",
                message=f"Health score below 70: {current_score}/100",
                metric="score", threshold=70, current_value=current_score,
            ))

        trends = self.get_trends(5)
        if len(trends) >= 2:
            prev = trends[-2].findings_count
            if prev > 0 and current_findings > prev * 1.5:
                alerts.append(Alert(
                    rule_id="ALERT003", severity="warning",
                    message=f"Findings increased by {((current_findings/prev)-1)*100:.0f}%",
                    metric="findings_count", threshold=prev * 1.5,
                    current_value=current_findings,
                ))

        with sqlite3.connect(self.db_path) as conn:
            for alert in alerts:
                conn.execute(
                    "INSERT INTO alerts (timestamp, rule_id, severity, message) VALUES (?, ?, ?, ?)",
                    (datetime.utcnow().isoformat(), alert.rule_id, alert.severity, alert.message),
                )

        return alerts
