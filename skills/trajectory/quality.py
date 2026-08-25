"""Verified quality memory and an explainable k-NN routing baseline.

This module is deliberately advisory.  It records only outcomes backed by an
external verifier, stores no raw task text, and never changes the active route.
The support set lives in the target project's ``.botte`` directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from skills.events import log_event

SCHEMA = "botte.quality-trajectory/v1"
EVENT_KIND = "qa_trajectory"
ADVICE_EVENT_KIND = "qa_shadow_advice"
FEATURE_VERSION = "hash-bow-v1"
FEATURE_DIMENSIONS = 128
MAX_ENTRIES = 5_000
MAX_BYTES = 8 * 1024 * 1024
MIN_SHADOW_SAMPLES = 5
MIN_NEIGHBORS = 3
MIN_ROUTE_SUPPORT = 2
MIN_G2_TRAJECTORIES = 2_000
QUALITY_FLOOR = 0.72

ROUTES = ("deterministic", "local", "cloud", "human")
ROUTE_COST_ORDER = ("deterministic", "local", "cloud")
VERDICTS = ("FAIL", "UNCERTAIN", "PASS", "PASS_ROBUST")
RISKS = ("low", "standard", "high", "critical")

_VERDICT_DEFAULTS = {
    "FAIL": 0.0,
    "UNCERTAIN": 0.4,
    "PASS": 0.8,
    "PASS_ROBUST": 1.0,
}
_VERDICT_RANGES = {
    "FAIL": (0.0, 0.25),
    "UNCERTAIN": (0.25, 0.60),
    "PASS": (0.60, 0.95),
    "PASS_ROBUST": (0.80, 1.0),
}
_VERIFIER_FAMILIES = {
    "benchmark", "ci", "deterministic", "harness", "human", "independent",
    "pytest", "replay", "schema", "tests",
}
_WORD = re.compile(r"[\w+#./-]+", re.UNICODE)
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_TRAJECTORY_ID = re.compile(r"^qa_[0-9a-f]{12}$")


@dataclass(frozen=True)
class RouteAdvice:
    """A shadow-only recommendation with enough evidence to audit it."""

    status: str
    recommendation: str | None
    evidence_strength: float
    reason: str
    verified_samples: int
    neighbor_count: int
    candidates: list[dict]
    neighbors: list[dict]
    shadow_only: bool = True
    acted: bool = False
    calibrated: bool = False
    human_gate: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _quality_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".botte" / "quality-trajectories.jsonl"


def _clean_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def _optional_text(value: object, *, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = " ".join(value.split())
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def _non_negative(value: float | int | None, *, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return value


def _normalise_tags(tags: Iterable[str]) -> tuple[str, ...]:
    if isinstance(tags, (str, bytes)) or tags is None:
        raise ValueError("tags must be a list of strings")
    cleaned = {
        _clean_text(tag, field="tag", maximum=64).casefold()
        for tag in tags
    }
    return tuple(sorted(cleaned))


def _task_material(task: str, task_type: str, tags: Sequence[str]) -> str:
    normal = unicodedata.normalize("NFKC", task).casefold()
    return "\n".join((normal, task_type.casefold(), "|".join(tags)))


def _feature_names(task: str, task_type: str, tags: Sequence[str]) -> list[str]:
    normal = unicodedata.normalize("NFKC", task).casefold()
    tokens = [token for token in _WORD.findall(normal) if len(token) > 1][:512]
    names = [f"w:{token}" for token in tokens]
    names.extend(f"b:{left}|{right}" for left, right in zip(tokens, tokens[1:]))
    names.append(f"length:{min(len(tokens) // 20, 10)}")
    if "\n" in task or "```" in task:
        names.append("shape:multiline_or_code")
    if any(mark in task for mark in ("/", "\\", ".py", ".js", ".ts", ".rs")):
        names.append("shape:path_or_source")
    if "?" in task:
        names.append("shape:question")
    if task_type:
        names.append(f"type:{task_type.casefold()}")
    names.extend(f"tag:{tag}" for tag in tags)
    return names or ["shape:empty"]


def embed_task(task: str, task_type: str = "", tags: Iterable[str] = ()) -> list[list[float]]:
    """Return a deterministic, normalized sparse feature vector.

    The task text is transformed in memory and is not included in the returned
    representation.  Stable hashing keeps the format dependency-free.
    """
    task = _clean_text(task, field="task", maximum=20_000)
    task_type = _optional_text(task_type, field="task_type", maximum=64)
    normal_tags = _normalise_tags(tags)
    buckets: dict[int, float] = defaultdict(float)
    for name in _feature_names(task, task_type, normal_tags):
        digest = hashlib.blake2b(
            name.encode("utf-8"), digest_size=8, person=b"botte-qa"
        ).digest()
        index = int.from_bytes(digest[:4], "big") % FEATURE_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        buckets[index] += sign
    norm = math.sqrt(sum(value * value for value in buckets.values())) or 1.0
    return [[index, round(value / norm, 7)] for index, value in sorted(buckets.items()) if value]


def _as_sparse(vector: object) -> dict[int, float]:
    if not isinstance(vector, list):
        return {}
    out: dict[int, float] = {}
    for item in vector:
        if not isinstance(item, list) or len(item) != 2:
            return {}
        index, value = item
        if isinstance(index, bool) or not isinstance(index, int):
            return {}
        if not 0 <= index < FEATURE_DIMENSIONS:
            return {}
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {}
        if not math.isfinite(float(value)):
            return {}
        out[index] = float(value)
    return out


def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    score = sum(value * right.get(index, 0.0) for index, value in left.items())
    return max(0.0, min(1.0, score))


def _valid_loaded_record(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("schema") != SCHEMA or item.get("verified") is not True:
        return False
    route, verdict = item.get("route"), item.get("verdict")
    if route not in ROUTES or verdict not in VERDICTS:
        return False
    if item.get("feature_version") != FEATURE_VERSION or not _as_sparse(item.get("features")):
        return False
    if not isinstance(item.get("id"), str) or not _TRAJECTORY_ID.fullmatch(item["id"]):
        return False
    if not isinstance(item.get("verified_by"), str) or not item["verified_by"]:
        return False
    verifier_family = item["verified_by"].casefold().split(":", 1)[0].replace("-", "_")
    if verifier_family not in _VERIFIER_FAMILIES:
        return False
    if item.get("raw_task_stored") is not False:
        return False
    if any(field in item for field in ("task", "prompt", "input_text")):
        return False
    fingerprint = item.get("task_fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        return False
    score = item.get("quality_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return False
    if not math.isfinite(float(score)):
        return False
    low, high = _VERDICT_RANGES[verdict]
    if not low <= float(score) <= high:
        return False
    for field in ("duration_ms", "cost_usd"):
        value = item.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or value < 0
        ):
            return False
    tokens = item.get("tokens")
    if tokens is not None and (
        isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0
    ):
        return False
    return True


def _rotate(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size <= MAX_BYTES:
            return
        all_lines = path.read_text(encoding="utf-8").splitlines()
        keep = min(MAX_ENTRIES, max(1, len(all_lines) // 2))
        lines = all_lines[-keep:]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError:
        return


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def record_verified(
    task: str,
    *,
    route: str,
    verdict: str,
    verified_by: str,
    project_root: str | Path = ".",
    task_type: str = "",
    tags: Iterable[str] = (),
    quality_score: float | None = None,
    risk: str = "standard",
    model: str = "",
    harness: str = "",
    duration_ms: float | None = None,
    cost_usd: float | None = None,
    tokens: int | None = None,
    evidence_refs: Iterable[str] = (),
) -> dict:
    """Persist one externally verified outcome and return its compact record."""
    task = _clean_text(task, field="task", maximum=20_000)
    route = str(route).strip().casefold()
    verdict = str(verdict).strip().upper().replace("-", "_")
    risk = str(risk).strip().casefold()
    if route not in ROUTES:
        raise ValueError(f"route must be one of: {', '.join(ROUTES)}")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of: {', '.join(VERDICTS)}")
    if risk not in RISKS:
        raise ValueError(f"risk must be one of: {', '.join(RISKS)}")

    verifier = _clean_text(verified_by, field="verified_by", maximum=128)
    family = verifier.casefold().split(":", 1)[0].replace("-", "_")
    if family not in _VERIFIER_FAMILIES:
        allowed = ", ".join(sorted(_VERIFIER_FAMILIES))
        raise ValueError(
            "verified_by must name an external verifier family "
            f"({allowed}); model self-reports are not labels"
        )

    if quality_score is not None and (
        isinstance(quality_score, bool) or not isinstance(quality_score, (int, float))
    ):
        raise ValueError("quality_score must be numeric")
    score = _VERDICT_DEFAULTS[verdict] if quality_score is None else float(quality_score)
    if not math.isfinite(score):
        raise ValueError("quality_score must be finite")
    low, high = _VERDICT_RANGES[verdict]
    if not low <= score <= high:
        raise ValueError(f"quality_score for {verdict} must be between {low} and {high}")

    duration_ms = _non_negative(duration_ms, field="duration_ms")
    cost_usd = _non_negative(cost_usd, field="cost_usd")
    tokens = _non_negative(tokens, field="tokens")
    if tokens is not None and not isinstance(tokens, int):
        raise ValueError("tokens must be an integer")
    normal_tags = _normalise_tags(tags)
    task_type = _optional_text(task_type, field="task_type", maximum=64)
    material = _task_material(task, task_type, normal_tags)
    if isinstance(evidence_refs, (str, bytes)) or evidence_refs is None:
        raise ValueError("evidence_refs must be a list of strings")
    evidence_values = list(evidence_refs)
    if len(evidence_values) > 20:
        raise ValueError("evidence_refs must contain at most 20 items")
    evidence = [_clean_text(ref, field="evidence_ref", maximum=256)
                for ref in evidence_values]
    now = time.time()
    record = {
        "schema": SCHEMA,
        "id": f"qa_{uuid.uuid4().hex[:12]}",
        "recorded_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "timestamp": now,
        "verified": True,
        "verified_by": verifier,
        "task_fingerprint": hashlib.sha256(material.encode("utf-8")).hexdigest(),
        "feature_version": FEATURE_VERSION,
        "features": embed_task(task, task_type, normal_tags),
        "task_type": task_type,
        "tags": list(normal_tags),
        "route": route,
        "verdict": verdict,
        "quality_score": round(score, 4),
        "risk": risk,
        "model": _optional_text(model, field="model", maximum=128),
        "harness": _optional_text(harness, field="harness", maximum=128),
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
        "tokens": tokens,
        "evidence_refs": evidence,
        "raw_task_stored": False,
    }
    _append(_quality_path(project_root), record)
    log_event(
        EVENT_KIND,
        project_root=project_root,
        trajectory_id=record["id"],
        route=route,
        verdict=verdict,
        quality_score=record["quality_score"],
        verified_by=verifier,
    )
    return record


def load_verified(project_root: str | Path = ".", limit: int = MAX_ENTRIES) -> list[dict]:
    """Load valid quality trajectories oldest-first; malformed rows are skipped."""
    try:
        lines = _quality_path(project_root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not _valid_loaded_record(item):
            continue
        records.append(item)
    return records


def _support_records(records: Iterable[dict]) -> list[dict]:
    """Keep the newest outcome per task/route so duplicates cannot inflate support."""
    by_task_route: dict[tuple[str, str], dict] = {}
    for item in records:
        key = (str(item.get("task_fingerprint", "")), str(item.get("route", "")))
        if key[0]:
            by_task_route[key] = item
    return list(by_task_route.values())


def _candidate_summary(items: list[tuple[float, dict]]) -> dict:
    weight = sum(max(similarity, 0.001) for similarity, _ in items)
    quality = sum(
        max(similarity, 0.001) * float(item["quality_score"])
        for similarity, item in items
    ) / weight
    pass_weight = sum(
        max(similarity, 0.001)
        for similarity, item in items
        if item["verdict"] in ("PASS", "PASS_ROBUST")
    )
    durations = [float(item["duration_ms"]) for _, item in items if item.get("duration_ms") is not None]
    costs = [float(item["cost_usd"]) for _, item in items if item.get("cost_usd") is not None]
    tokens = [int(item["tokens"]) for _, item in items if item.get("tokens") is not None]
    return {
        "route": items[0][1]["route"],
        "support": len(items),
        "weighted_quality": round(quality, 4),
        "weighted_pass_rate": round(pass_weight / weight, 4),
        "mean_similarity": round(sum(sim for sim, _ in items) / len(items), 4),
        "mean_duration_ms": round(sum(durations) / len(durations), 2) if durations else None,
        "mean_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "mean_tokens": round(sum(tokens) / len(tokens), 1) if tokens else None,
    }


def _emit_advice(project_root: str | Path, task_fingerprint: str, advice: RouteAdvice) -> None:
    log_event(
        ADVICE_EVENT_KIND,
        project_root=project_root,
        task_fingerprint=task_fingerprint,
        status=advice.status,
        recommendation=advice.recommendation,
        evidence_strength=advice.evidence_strength,
        neighbor_count=advice.neighbor_count,
        shadow_only=True,
        acted=False,
    )


def advise_route(
    task: str,
    *,
    project_root: str | Path = ".",
    task_type: str = "",
    tags: Iterable[str] = (),
    risk: str = "standard",
    k: int = 7,
    min_similarity: float = 0.08,
) -> RouteAdvice:
    """Recommend a route from verified neighbors without changing execution."""
    task = _clean_text(task, field="task", maximum=20_000)
    risk = str(risk).strip().casefold()
    if risk not in RISKS:
        raise ValueError(f"risk must be one of: {', '.join(RISKS)}")
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 50:
        raise ValueError("k must be between 1 and 50")
    if (isinstance(min_similarity, bool)
            or not isinstance(min_similarity, (int, float))
            or not 0.0 <= float(min_similarity) <= 1.0):
        raise ValueError("min_similarity must be between 0 and 1")

    normal_tags = _normalise_tags(tags)
    task_type = _optional_text(task_type, field="task_type", maximum=64)
    material = _task_material(task, task_type, normal_tags)
    fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()
    recorded = load_verified(project_root)
    records = _support_records(recorded)

    if risk in ("high", "critical"):
        advice = RouteAdvice(
            status="gated",
            recommendation="human",
            evidence_strength=1.0,
            reason="High-impact work keeps a deterministic human approval gate; k-NN is bypassed.",
            verified_samples=len(records),
            neighbor_count=0,
            candidates=[],
            neighbors=[],
            human_gate=True,
        )
        _emit_advice(project_root, fingerprint, advice)
        return advice

    if len(records) < MIN_SHADOW_SAMPLES:
        remaining = MIN_SHADOW_SAMPLES - len(records)
        advice = RouteAdvice(
            status="collecting",
            recommendation=None,
            evidence_strength=0.0,
            reason=f"Collect {remaining} more verified outcome(s) before the first shadow suggestion.",
            verified_samples=len(records),
            neighbor_count=0,
            candidates=[],
            neighbors=[],
        )
        _emit_advice(project_root, fingerprint, advice)
        return advice

    query = _as_sparse(embed_task(task, task_type, normal_tags))
    scored = [
        (_cosine(query, _as_sparse(item.get("features"))), item)
        for item in records
    ]
    neighbors = [pair for pair in sorted(scored, key=lambda pair: pair[0], reverse=True)
                 if pair[0] >= min_similarity][:k]
    compact_neighbors = [
        {
            "id": item["id"],
            "similarity": round(similarity, 4),
            "route": item["route"],
            "verdict": item["verdict"],
            "verified_by": item["verified_by"],
        }
        for similarity, item in neighbors
    ]
    if len(neighbors) < MIN_NEIGHBORS:
        advice = RouteAdvice(
            status="abstain",
            recommendation=None,
            evidence_strength=0.0,
            reason="Too few similar verified outcomes; keep the current deterministic router in control.",
            verified_samples=len(records),
            neighbor_count=len(neighbors),
            candidates=[],
            neighbors=compact_neighbors,
        )
        _emit_advice(project_root, fingerprint, advice)
        return advice

    grouped: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for similarity, item in neighbors:
        grouped[item["route"]].append((similarity, item))
    candidates = [_candidate_summary(items) for items in grouped.values()]
    candidates.sort(key=lambda item: ROUTES.index(item["route"]))
    by_route = {item["route"]: item for item in candidates}
    recommendation = next((
        route for route in ROUTE_COST_ORDER
        if route in by_route
        and by_route[route]["support"] >= MIN_ROUTE_SUPPORT
        and by_route[route]["weighted_quality"] >= QUALITY_FLOOR
    ), None)

    if recommendation is None:
        advice = RouteAdvice(
            status="abstain",
            recommendation=None,
            evidence_strength=0.0,
            reason="No route has enough similar support above the verified quality floor.",
            verified_samples=len(records),
            neighbor_count=len(neighbors),
            candidates=candidates,
            neighbors=compact_neighbors,
        )
        _emit_advice(project_root, fingerprint, advice)
        return advice

    chosen = by_route[recommendation]
    evidence_strength = min(0.95, (
        0.5 * chosen["mean_similarity"]
        + 0.3 * chosen["weighted_quality"]
        + 0.2 * min(1.0, chosen["support"] / 5)
    ))
    advice = RouteAdvice(
        status="suggest",
        recommendation=recommendation,
        evidence_strength=round(evidence_strength, 4),
        reason=(
            f"{recommendation} is the least expensive route above the quality floor "
            f"with {chosen['support']} verified neighbor(s)."
        ),
        verified_samples=len(records),
        neighbor_count=len(neighbors),
        candidates=candidates,
        neighbors=compact_neighbors,
    )
    _emit_advice(project_root, fingerprint, advice)
    return advice


def quality_status(project_root: str | Path = ".") -> dict:
    """Summarize ledger quality and state the single next maturation step."""
    recorded = load_verified(project_root)
    records = _support_records(recorded)
    total = len(records)
    route_counts = Counter(item["route"] for item in records)
    verdict_counts = Counter(item["verdict"] for item in records)
    verifier_counts = Counter(item["verified_by"].split(":", 1)[0] for item in records)
    if total == 0:
        readiness = "empty"
        next_action = "Record the first externally verified outcome."
    elif total < MIN_SHADOW_SAMPLES:
        readiness = "collecting"
        next_action = f"Record {MIN_SHADOW_SAMPLES - total} more verified outcome(s)."
    elif total < MIN_G2_TRAJECTORIES:
        readiness = "shadow"
        next_action = (
            f"Keep comparing k-NN with the deterministic baseline; "
            f"{MIN_G2_TRAJECTORIES - total} verified outcomes remain before G2 evaluation."
        )
    else:
        readiness = "evaluation_due"
        next_action = "Run temporal holdout, calibration, ablation, drift, and rollback tests."
    average_quality = (
        sum(float(item["quality_score"]) for item in records) / total if total else None
    )
    return {
        "schema": "botte.quality-status/v1",
        "mode": "shadow",
        "readiness": readiness,
        "recorded_outcomes": len(recorded),
        "verified_samples": total,
        "unique_tasks": len({item["task_fingerprint"] for item in records}),
        "average_quality": round(average_quality, 4) if average_quality is not None else None,
        "by_route": {route: route_counts.get(route, 0) for route in ROUTES},
        "by_verdict": {verdict: verdict_counts.get(verdict, 0) for verdict in VERDICTS},
        "by_verifier": dict(sorted(verifier_counts.items())),
        "g2_min_verified": MIN_G2_TRAJECTORIES,
        "grounding_deduplication": "latest_per_task_route",
        "activation_allowed": False,
        "raw_task_storage": False,
        "storage": str(_quality_path(project_root)),
        "next_action": next_action,
    }


__all__ = [
    "RouteAdvice", "advise_route", "embed_task", "load_verified",
    "quality_status", "record_verified",
]
