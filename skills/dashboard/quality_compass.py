"""Privacy-aware Quality Compass data for the local dashboard.

The card consumes the verified shadow ledger from Quality Compass Wave 1 and,
when present, the bounded ``botte.quality-outcome/v1`` envelopes from Wave 2.
It summarizes local evidence without copying task fingerprints into its output.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from skills.trajectory.quality import (
    MIN_SHADOW_SAMPLES,
    ROUTES,
    load_verified,
)

OUTCOME_SCHEMA = "botte.quality-outcome/v1"
CARD_SCHEMA = "botte.quality-compass-card/v1"
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60
_OUTCOME_ID = re.compile(r"^qo_[0-9a-f]{16}$")
_PRIVATE_FIELDS = {"task", "prompt", "input_text", "answer"}
_SUCCESS = {"PASS", "PASS_ROBUST"}


def _finite_metric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _valid_outcome(item: object) -> bool:
    if not isinstance(item, dict) or item.get("schema") != OUTCOME_SCHEMA:
        return False
    if _PRIVATE_FIELDS.intersection(item):
        return False
    if item.get("raw_task_stored") is not False:
        return False
    if item.get("shadow_only") is not True or item.get("activation_allowed") is not False:
        return False
    outcome_id = item.get("id")
    if not isinstance(outcome_id, str) or not _OUTCOME_ID.fullmatch(outcome_id):
        return False
    if item.get("route") not in ROUTES:
        return False
    return _finite_metric(item.get("timestamp")) is not None


def _load_outcomes(project_root: str | Path, limit: int = 5_000) -> list[dict]:
    path = Path(project_root).resolve() / ".botte" / "quality-outcomes.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    outcomes: list[dict] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if _valid_outcome(item):
            outcomes.append(item)
    return outcomes


def _deduplicated(records: Iterable[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for record in records:
        fingerprint = record.get("task_fingerprint")
        route = record.get("route")
        if isinstance(fingerprint, str) and route in ROUTES:
            latest[(fingerprint, route)] = record
    return list(latest.values())


def _mean(values: Iterable[object], *, digits: int = 2) -> float | None:
    numbers = [number for value in values if (number := _finite_metric(value)) is not None]
    return round(sum(numbers) / len(numbers), digits) if numbers else None


def _route_comparison(records: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("route", ""))].append(record)
    comparison = []
    for route in ROUTES:
        rows = grouped.get(route, [])
        if not rows:
            continue
        passed = sum(record.get("verdict") in _SUCCESS for record in rows)
        comparison.append({
            "route": route,
            "verified": len(rows),
            "pass_rate": round(passed / len(rows), 4),
            "mean_quality": _mean((row.get("quality_score") for row in rows), digits=4),
            "mean_duration_ms": _mean(row.get("duration_ms") for row in rows),
            "mean_cost_usd": _mean((row.get("cost_usd") for row in rows), digits=6),
            "mean_tokens": _mean((row.get("tokens") for row in rows), digits=1),
        })
    return comparison


def _conflicts(records: list[dict]) -> tuple[int, int]:
    verdicts: dict[str, set[str]] = defaultdict(set)
    for record in records:
        fingerprint = record.get("task_fingerprint")
        verdict = record.get("verdict")
        if isinstance(fingerprint, str) and isinstance(verdict, str):
            verdicts[fingerprint].add(verdict)
    conflicts = sum(
        bool(values & _SUCCESS) and bool(values - _SUCCESS)
        for values in verdicts.values()
    )
    return conflicts, len(verdicts)


def _latest_evidence(records: list[dict], limit: int = 5) -> list[dict]:
    ordered = sorted(records, key=lambda row: float(row.get("timestamp", 0)), reverse=True)
    result = []
    for row in ordered[:limit]:
        refs = row.get("evidence_refs")
        result.append({
            "id": row.get("id", ""),
            "recorded_at": row.get("recorded_at"),
            "route": row.get("route", ""),
            "verdict": row.get("verdict", "UNCERTAIN"),
            "verified_by": row.get("verified_by", ""),
            "evidence_refs": list(refs[:5]) if isinstance(refs, list) else [],
        })
    return result


def _versions(outcomes: list[dict], records: list[dict]) -> dict:
    models = sorted({str(row.get("model")) for row in (*outcomes, *records) if row.get("model")})
    harnesses = sorted({str(row.get("harness")) for row in (*outcomes, *records) if row.get("harness")})
    tools: dict[str, str] = {}
    for row in outcomes:
        values = row.get("tool_versions")
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(key, str) and isinstance(value, str):
                    tools[key] = value
    return {"models": models[:10], "harnesses": harnesses[:10], "tools": tools}


def quality_compass_card(project_root: str | Path = ".", *, now: float | None = None) -> dict:
    """Return the local three-line verdict and progressively disclosed evidence."""
    now = time.time() if now is None else float(now)
    recorded = load_verified(project_root)
    records = _deduplicated(recorded)
    outcomes = _load_outcomes(project_root)
    total = len(records)
    conflicts, unique_tasks = _conflicts(records)

    timestamps = [
        float(row["timestamp"])
        for row in (*outcomes, *records)
        if isinstance(row.get("timestamp"), (int, float))
    ]
    latest_timestamp = max(timestamps) if timestamps else None
    age_seconds = max(0.0, now - latest_timestamp) if latest_timestamp is not None else None
    freshness = (
        "unknown" if age_seconds is None else
        "stale" if age_seconds > STALE_AFTER_SECONDS else
        "current"
    )
    latest_outcome = max(outcomes, key=lambda row: float(row["timestamp"])) if outcomes else None
    human_gate = bool(latest_outcome and (
        latest_outcome.get("approval_required") is True
        or latest_outcome.get("status") == "APPROVAL_REQUIRED"
        or latest_outcome.get("risk") in ("high", "critical")
    ))

    if human_gate:
        state = "human_gated"
        label = "Human approval required"
        reason = "The latest high-impact outcome is stopped at the human gate."
        next_action = "Review the evidence and approve or reject explicitly; no learned route may act."
    elif total == 0:
        state = "empty"
        label = "No verified quality evidence"
        reason = "The private quality ledger has no independently verified outcome yet."
        next_action = "Record the first externally verified result; keep deterministic routing in control."
    elif total < MIN_SHADOW_SAMPLES:
        remaining = MIN_SHADOW_SAMPLES - total
        state = "collecting"
        label = "Collecting verified evidence"
        reason = f"{total} of {MIN_SHADOW_SAMPLES} outcomes support the first shadow comparison."
        next_action = f"Collect {remaining} more independent outcome(s); do not activate learned advice."
    elif conflicts:
        state = "conflicting"
        label = "Evidence conflicts"
        reason = f"{conflicts} recurrent task group(s) have incompatible verified verdicts."
        next_action = "Replay the conflicting cases with an independent verifier before trusting a route."
    elif freshness == "stale":
        state = "stale"
        label = "Evidence is stale"
        reason = "The newest verified quality signal is more than seven days old."
        next_action = "Run a fresh deterministic replay before using the shadow recommendation."
    else:
        state = "grounded"
        label = "Grounded for shadow comparison"
        reason = f"{total} de-duplicated outcomes provide current, non-conflicting support."
        next_action = "Compare shadow advice with the deterministic baseline; keep ACT disabled."

    abstentions = sum(bool(row.get("abstained")) for row in outcomes)
    escalations = sum(bool(row.get("escalated")) for row in outcomes)
    approval_count = sum(bool(row.get("approval_required")) for row in outcomes)
    coverage = min(1.0, total / MIN_SHADOW_SAMPLES)
    return {
        "schema": CARD_SCHEMA,
        "mode": "shadow",
        "state": state,
        "label": label,
        "reason": reason,
        "next_action": next_action,
        "human_gate": human_gate,
        "activation_allowed": False,
        "source_contract": OUTCOME_SCHEMA if outcomes else "botte.quality-trajectory/v1",
        "summary": {
            "verified_samples": total,
            "recorded_outcomes": len(outcomes),
            "unique_tasks": unique_tasks,
            "grounding_coverage": round(coverage, 4),
            "grounding_target": MIN_SHADOW_SAMPLES,
            "abstention_rate": round(abstentions / len(outcomes), 4) if outcomes else None,
            "escalations": escalations,
            "approval_required": approval_count,
            "freshness": freshness,
            "latest_recorded_at": max(
                (str(row.get("recorded_at")) for row in (*outcomes, *records) if row.get("recorded_at")),
                default=None,
            ),
        },
        "route_comparison": _route_comparison(records),
        "resources": {
            "mean_duration_ms": _mean(row.get("duration_ms") for row in outcomes or records),
            "mean_cost_usd": _mean((row.get("cost_usd") for row in outcomes or records), digits=6),
            "mean_tokens": _mean((row.get("tokens") for row in outcomes or records), digits=1),
            "mean_memory_mb": _mean(row.get("memory_mb") for row in outcomes),
            "mean_energy_wh": _mean((row.get("energy_wh") for row in outcomes), digits=4),
        },
        "versions": _versions(outcomes, records),
        "drift": {
            "status": "conflicting" if conflicts else freshness,
            "conflicting_tasks": conflicts,
            "conflict_rate": round(conflicts / unique_tasks, 4) if unique_tasks else 0.0,
            "stale_after_seconds": STALE_AFTER_SECONDS,
        },
        "supporting_evidence": _latest_evidence(records),
    }


def public_quality_compass_card() -> dict:
    """Return a useful public placeholder without copying local QA material."""
    return {
        "schema": CARD_SCHEMA,
        "mode": "shadow",
        "state": "private",
        "label": "Quality evidence stays local",
        "reason": "Private execution evidence is intentionally excluded from this public snapshot.",
        "next_action": "Open the loopback dashboard to inspect verified quality evidence.",
        "human_gate": False,
        "activation_allowed": False,
        "public_snapshot": True,
    }


__all__ = ["quality_compass_card", "public_quality_compass_card"]
