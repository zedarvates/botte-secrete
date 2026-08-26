"""Leakage-resistant shadow benchmark for routing mechanisms.

The harness compares deterministic effort rules, verified k-NN memory, and the
existing ``binary_router`` micro-NN on one sanitized temporal holdout.  It never
executes a model, trains weights, changes routing, or promotes a candidate.
When verified replayable missions are absent or insufficient, it emits a
machine-readable evidence-gap report instead of manufacturing a winner.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from skills.auto_router.effort import estimate as estimate_effort
from skills.auto_router.nn_belt import binary_router_prediction, confident_hint
from skills.nn_audit.audit import audit_models
from skills.tiered_router import Tier
from skills.trajectory.quality import advise_route, load_verified, record_verified

REPORT_SCHEMA = "botte.quality-routing-benchmark/v1"
MISSION_SCHEMA = "botte.quality-routing-mission/v1"
ROUTING_MECHANISMS = ("deterministic", "knn", "micro_nn")
MIN_TRAIN = 50
MIN_HOLDOUT = 20
MIN_TRAIN_FAMILIES = 10
MIN_HOLDOUT_FAMILIES = 5
QUALITY_FLOOR = 0.72
IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[2]

_MISSION_ID = re.compile(r"^qm_[0-9a-f]{12}$")
_FAMILY_ID = re.compile(r"^qf_[0-9a-f]{12}$")
_PRIVATE_PATTERNS = (
    re.compile(r"(?:^|\s)(?:/(?:home|Users|workspace|root|tmp|var|etc|opt|srv|mnt)/|[A-Za-z]:\\)"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[opusr]_[A-Za-z0-9]{12,})\b"),
)
_VERIFIERS = {
    "benchmark", "ci", "deterministic", "harness", "human", "independent",
    "pytest", "replay", "schema", "tests",
}


@dataclass(frozen=True)
class Mission:
    mission_id: str
    family_id: str
    observed_at: datetime
    task: str
    task_type: str
    expected_route: str
    verdict: str
    verified_by: str
    evidence_refs: tuple[str, ...]
    dataset_class: str


@dataclass(frozen=True)
class BenchmarkConfig:
    holdout_fraction: float = 0.25
    budget_ratio: float = 1.0
    has_local: bool = True
    min_train: int = MIN_TRAIN
    min_holdout: int = MIN_HOLDOUT
    min_train_families: int = MIN_TRAIN_FAMILIES
    min_holdout_families: int = MIN_HOLDOUT_FAMILIES
    quality_floor: float = QUALITY_FLOOR

    def validate(self) -> None:
        if not 0.1 <= self.holdout_fraction <= 0.5:
            raise ValueError("holdout_fraction must be between 0.1 and 0.5")
        if not 0.0 <= self.budget_ratio <= 1.0:
            raise ValueError("budget_ratio must be between 0 and 1")
        for name in ("min_train", "min_holdout", "min_train_families", "min_holdout_families"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not 0.0 <= self.quality_floor <= 1.0:
            raise ValueError("quality_floor must be between 0 and 1")


class MissionValidationError(ValueError):
    """A mission set cannot be trusted or safely benchmarked."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise MissionValidationError("invalid_timestamp", "observed_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MissionValidationError("invalid_timestamp", "observed_at is not valid ISO-8601") from error
    if parsed.tzinfo is None:
        raise MissionValidationError("invalid_timestamp", "observed_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _clean_string(value: object, field: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise MissionValidationError("invalid_mission", f"{field} must be a string")
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise MissionValidationError("invalid_mission", f"{field} must not be empty")
    if len(cleaned) > maximum:
        raise MissionValidationError("invalid_mission", f"{field} exceeds {maximum} characters")
    return cleaned


def _validate_task(task: str) -> None:
    if any(pattern.search(task) for pattern in _PRIVATE_PATTERNS):
        raise MissionValidationError(
            "unsanitized_task",
            "mission task contains a local path, address, private endpoint, or credential-like token",
        )


def _mission(item: object) -> Mission:
    if not isinstance(item, dict) or item.get("schema") != MISSION_SCHEMA:
        raise MissionValidationError("invalid_mission", f"mission schema must be {MISSION_SCHEMA}")
    if item.get("sanitized") is not True or item.get("contains_private_data") is not False:
        raise MissionValidationError("unsanitized_task", "missions must assert sanitized=true and contains_private_data=false")
    mission_id = _clean_string(item.get("id"), "id", 15)
    family_id = _clean_string(item.get("family_id"), "family_id", 15)
    if not _MISSION_ID.fullmatch(mission_id) or not _FAMILY_ID.fullmatch(family_id):
        raise MissionValidationError("invalid_mission", "mission and family IDs must be opaque bounded identifiers")
    task = _clean_string(item.get("task"), "task", 2_000)
    _validate_task(task)
    task_type = _clean_string(item.get("task_type", ""), "task_type", 64, required=False)
    route = _clean_string(item.get("expected_route"), "expected_route", 16).casefold()
    if route not in ("local", "cloud"):
        raise MissionValidationError("invalid_route_oracle", "expected_route must be local or cloud")
    verdict = _clean_string(item.get("verdict"), "verdict", 16).upper().replace("-", "_")
    if verdict not in ("PASS", "PASS_ROBUST"):
        raise MissionValidationError("invalid_route_oracle", "routing oracles require PASS or PASS_ROBUST evidence")
    verified_by = _clean_string(item.get("verified_by"), "verified_by", 128)
    family = verified_by.casefold().split(":", 1)[0].replace("-", "_")
    if family not in _VERIFIERS:
        raise MissionValidationError("untrusted_verifier", "verified_by must name an independent verifier family")
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 20:
        raise MissionValidationError("missing_evidence", "evidence_refs must contain 1 to 20 references")
    evidence = tuple(_clean_string(ref, "evidence_ref", 256) for ref in refs)
    dataset_class = _clean_string(item.get("dataset_class"), "dataset_class", 16).casefold()
    if dataset_class not in ("verified", "fixture"):
        raise MissionValidationError("invalid_mission", "dataset_class must be verified or fixture")
    return Mission(
        mission_id=mission_id,
        family_id=family_id,
        observed_at=_parse_timestamp(item.get("observed_at")),
        task=task,
        task_type=task_type,
        expected_route=route,
        verdict=verdict,
        verified_by=verified_by,
        evidence_refs=evidence,
        dataset_class=dataset_class,
    )


def load_missions(path: str | Path) -> list[Mission]:
    """Load a bounded JSONL mission set; fail closed on malformed/private rows."""
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MissionValidationError("mission_set_unavailable", "mission set cannot be read") from error
    if len(lines) > 10_000:
        raise MissionValidationError("mission_set_too_large", "mission set exceeds 10,000 rows")
    missions: list[Mission] = []
    ids: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise MissionValidationError("invalid_json", f"invalid JSON at row {line_number}") from error
        mission = _mission(item)
        if mission.mission_id in ids:
            raise MissionValidationError("duplicate_mission_id", "mission IDs must be unique")
        ids.add(mission.mission_id)
        missions.append(mission)
    return sorted(missions, key=lambda item: (item.observed_at, item.mission_id))


def _task_digest(task: str) -> str:
    normal = " ".join(task.casefold().split())
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()


def temporal_split(missions: Sequence[Mission], config: BenchmarkConfig) -> tuple[list[Mission], list[Mission], list[dict]]:
    """Split oldest/newest and report exact-task or family leakage explicitly."""
    config.validate()
    if len(missions) < 2:
        return list(missions), [], [{"code": "temporal_holdout_unavailable", "detail": "At least two dated missions are required."}]
    holdout_size = max(1, math.ceil(len(missions) * config.holdout_fraction))
    train = list(missions[:-holdout_size])
    holdout = list(missions[-holdout_size:])
    gaps: list[dict] = []
    if train and holdout and train[-1].observed_at >= holdout[0].observed_at:
        gaps.append({"code": "temporal_boundary_not_strict", "detail": "Train and holdout timestamps overlap at the boundary."})
    train_tasks = {_task_digest(item.task) for item in train}
    holdout_tasks = {_task_digest(item.task) for item in holdout}
    duplicate_count = len(train_tasks & holdout_tasks)
    if duplicate_count:
        gaps.append({"code": "exact_task_leakage", "count": duplicate_count, "detail": "Normalized task duplicates cross the temporal boundary."})
    train_families = {item.family_id for item in train}
    holdout_families = {item.family_id for item in holdout}
    family_count = len(train_families & holdout_families)
    if family_count:
        gaps.append({"code": "task_family_leakage", "count": family_count, "detail": "Task families cross the temporal boundary."})
    if len(train) < config.min_train:
        gaps.append({"code": "train_below_minimum", "observed": len(train), "required": config.min_train})
    if len(holdout) < config.min_holdout:
        gaps.append({"code": "holdout_below_minimum", "observed": len(holdout), "required": config.min_holdout})
    if len(train_families) < config.min_train_families:
        gaps.append({"code": "train_family_diversity_low", "observed": len(train_families), "required": config.min_train_families})
    if len(holdout_families) < config.min_holdout_families:
        gaps.append({"code": "holdout_family_diversity_low", "observed": len(holdout_families), "required": config.min_holdout_families})
    for split_name, rows in (("train", train), ("holdout", holdout)):
        routes = {row.expected_route for row in rows}
        if routes != {"local", "cloud"}:
            gaps.append({"code": f"{split_name}_route_coverage_incomplete", "observed": sorted(routes), "required": ["cloud", "local"]})
    return train, holdout, gaps


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 4)


def _wilson(successes: int, total: int, z: float = 1.96) -> dict:
    if total <= 0:
        return {"low": None, "high": None, "confidence": 0.95}
    rate = successes / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total) / denominator
    return {"low": round(max(0.0, centre - margin), 4), "high": round(min(1.0, centre + margin), 4), "confidence": 0.95}


def _expected_calibration_error(observations: Sequence[tuple[float, int]], bins: int = 10) -> float | None:
    """Return equal-width ECE without inventing confidence for abstentions."""
    if not observations:
        return None
    total = len(observations)
    error = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [
            item for item in observations
            if low <= item[0] and (item[0] < high or (index == bins - 1 and item[0] <= high))
        ]
        if not bucket:
            continue
        mean_confidence = sum(item[0] for item in bucket) / len(bucket)
        mean_accuracy = sum(item[1] for item in bucket) / len(bucket)
        error += len(bucket) / total * abs(mean_confidence - mean_accuracy)
    return round(error, 4)


def _evaluate(name: str, holdout: Sequence[Mission], predict: Callable[[Mission], tuple[str | None, float | None]], *, setup_ms: float = 0.0, calibration: bool = False) -> tuple[dict, dict[str, str | None]]:
    latencies: list[float] = []
    rows: dict[str, str | None] = {}
    confidences: list[tuple[float, int]] = []
    verdicts = {"PASS": 0, "FAIL": 0, "UNCERTAIN": 0}
    correct = abstained = cloud = 0
    tracemalloc.start()
    try:
        for mission in holdout:
            started = time.perf_counter_ns()
            prediction, confidence = predict(mission)
            latencies.append((time.perf_counter_ns() - started) / 1_000_000)
            rows[mission.mission_id] = prediction
            if prediction is None:
                abstained += 1
                verdicts["UNCERTAIN"] += 1
            elif prediction == mission.expected_route:
                correct += 1
                verdicts["PASS"] += 1
            else:
                verdicts["FAIL"] += 1
            cloud += prediction == "cloud"
            if calibration and confidence is not None and prediction is not None:
                confidences.append((confidence, int(prediction == mission.expected_route)))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    total = len(holdout)
    non_abstained = total - abstained
    ece = _expected_calibration_error(confidences)
    return ({
        "mechanism": name,
        "status": "measured",
        "quality_scope": "routing_oracle_only",
        "holdout_missions": total,
        "correct_routes": correct,
        "mission_success_rate": round(correct / total, 4) if total else None,
        "accuracy_non_abstained": round(correct / non_abstained, 4) if non_abstained else None,
        "coverage": round(non_abstained / total, 4) if total else None,
        "abstention_rate": round(abstained / total, 4) if total else None,
        "escalation_rate": round(cloud / total, 4) if total else None,
        "qualitative_verdicts": verdicts,
        "confidence_interval": _wilson(correct, total),
        "calibration_ece": ece,
        "latency_ms": {
            "setup": round(setup_ms, 4),
            "cold_first": round(latencies[0], 4) if latencies else None,
            "warm_p50": round(statistics.median(latencies[1:]), 4) if len(latencies) > 1 else None,
            "warm_p95": _percentile(latencies[1:], 0.95),
        },
        "decision_tokens": 0,
        "decision_cost_usd": 0.0,
        "peak_python_memory_bytes": peak,
        "vram_peak_mb": None,
        "recommendation": "collect_more_data",
        "activation_allowed": False,
    }, rows)


def _deterministic(mission: Mission) -> tuple[str, None]:
    effort = estimate_effort(mission.task, task_type=mission.task_type)
    return ("local" if effort.tier <= Tier.LOCAL else "cloud"), None


def _micro_nn(config: BenchmarkConfig) -> Callable[[Mission], tuple[str | None, float | None]]:
    def predict(mission: Mission) -> tuple[str | None, float | None]:
        effort = estimate_effort(mission.task, task_type=mission.task_type)
        raw = binary_router_prediction(effort.score, config.budget_ratio, config.has_local)
        hint = confident_hint(raw)
        return (hint[0], float(raw["confidence"])) if hint and raw else (None, float(raw["confidence"]) if raw else None)
    return predict


def _knn(train: Sequence[Mission]) -> tuple[Callable[[Mission], tuple[str | None, float | None]], tempfile.TemporaryDirectory, float]:
    temporary = tempfile.TemporaryDirectory()
    started = time.perf_counter_ns()
    for mission in train:
        record_verified(
            mission.task,
            project_root=temporary.name,
            route=mission.expected_route,
            verdict=mission.verdict,
            verified_by=mission.verified_by,
            task_type=mission.task_type,
            evidence_refs=mission.evidence_refs,
        )
    setup_ms = (time.perf_counter_ns() - started) / 1_000_000

    def predict(mission: Mission) -> tuple[str | None, float | None]:
        advice = advise_route(
            mission.task,
            project_root=temporary.name,
            task_type=mission.task_type,
            risk="standard",
        )
        return advice.recommendation, advice.evidence_strength
    return predict, temporary, setup_ms


def _active_feedback_count(path: Path | None = None) -> int:
    source = path or (Path.home() / ".cache" / "botte" / "active_learning" / "inference_logs.jsonl")
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    verified: set[str] = set()
    for line in lines:
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if (item.get("model_name") == "binary_router" and item.get("verified") is True
                and item.get("actual_class") in (0, 1) and item.get("sample_fingerprint")):
            verified.add(str(item["sample_fingerprint"]))
    return len(verified)


def _reproducibility(mission_path: Path | None, code_ref: str, config: BenchmarkConfig) -> dict:
    module_root = Path(__file__).resolve().parent
    model = IMPLEMENTATION_ROOT / "skills" / "botte_nn" / "models" / "binary_router.json"
    return {
        "code_ref": code_ref or None,
        "mission_set_sha256": _sha256(mission_path) if mission_path else None,
        "benchmark_harness_sha256": _sha256(Path(__file__)),
        "quality_module_sha256": _sha256(module_root / "quality.py"),
        "micro_nn_model": "binary_router",
        "micro_nn_model_sha256": _sha256(model),
        "deterministic_policy": "effort-tier-v1",
        "knn_feature_version": "hash-bow-v1",
        "budget_ratio": config.budget_ratio,
        "has_local_surface": config.has_local,
    }


def _base_report(project_root: Path, mission_path: Path | None, code_ref: str, config: BenchmarkConfig) -> dict:
    verified = load_verified(project_root)
    audit = audit_models(IMPLEMENTATION_ROOT / "skills" / "botte_nn", IMPLEMENTATION_ROOT / "skills")
    binary = next((item for item in audit.get("models", []) if item.get("model") == "binary_router"), None)
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow",
        "benchmark_status": "insufficient_evidence",
        "conclusion": "Collect more independently verified, replayable missions; no mechanism can be ranked honestly yet.",
        "comparative_winner": None,
        "dataset": {
            "provided": mission_path is not None,
            "dataset_class": None,
            "missions": 0,
            "train": 0,
            "holdout": 0,
            "train_families": 0,
            "holdout_families": 0,
            "temporal_order": "oldest_train_newest_holdout",
            "exact_task_leakage": None,
            "task_family_leakage": None,
            "eligible_for_conclusions": False,
            "raw_tasks_in_report": False,
        },
        "evidence_inventory": {
            "verified_quality_rows": len(verified),
            "replayable_quality_missions": 0,
            "verified_binary_router_feedback": _active_feedback_count(),
            "micro_nn_inventory": audit.get("summary", {}),
            "binary_router_candidate": {
                "present": binary is not None,
                "audit_verdict": binary.get("verdict") if binary else "missing",
                "wired": bool(binary and binary.get("wired")),
                "benchmark_eligible": False,
            },
        },
        "routing_quality": {
            name: {"mechanism": name, "status": "not_run", "recommendation": "collect_more_data", "activation_allowed": False}
            for name in ROUTING_MECHANISMS
        },
        "model_quality": {"status": "not_observed", "reason": "The routing harness does not execute or judge model answers."},
        "harness_quality": {"status": "not_observed", "reason": "No independently verified harness outcomes are replayable in this environment."},
        "disagreement": {"status": "not_observed", "pairwise_rates": {}},
        "missing_metrics": [
            {"metric": "model_answer_quality", "reason": "No verified answer outputs are in the mission contract."},
            {"metric": "harness_recovery_quality", "reason": "No verified harness replay outcomes are available."},
            {"metric": "execution_tokens_and_cost", "reason": "This run evaluates decision functions only and executes no model."},
            {"metric": "ram_rss", "reason": "Only Python allocation peak is observable with the dependency-free harness."},
            {"metric": "vram_peak", "reason": "No model is executed and no portable VRAM sampler is available."},
            {"metric": "energy", "reason": "No portable process-level energy meter is available in this environment."},
        ],
        "gaps": [],
        "reproducibility": _reproducibility(mission_path, code_ref, config),
        "authority": {"shadow_only": True, "acted": False, "trained": False, "activation_allowed": False},
    }


def _pairwise(predictions: dict[str, dict[str, str | None]]) -> dict:
    rates: dict[str, float | None] = {}
    for index, left in enumerate(ROUTING_MECHANISMS):
        for right in ROUTING_MECHANISMS[index + 1:]:
            common = sorted(set(predictions[left]) & set(predictions[right]))
            observed = [(predictions[left][key], predictions[right][key]) for key in common]
            comparable = [(a, b) for a, b in observed if a is not None and b is not None]
            rates[f"{left}_vs_{right}"] = (
                round(sum(a != b for a, b in comparable) / len(comparable), 4)
                if comparable else None
            )
    return rates


def _recommend(report: dict, eligible: bool, quality_floor: float) -> None:
    routing = report["routing_quality"]
    if not eligible:
        return
    baseline = routing["deterministic"]
    baseline_rate = baseline.get("mission_success_rate")
    baseline["recommendation"] = "keep"
    for name in ("knn", "micro_nn"):
        candidate = routing[name]
        rate = candidate.get("mission_success_rate")
        interval = candidate.get("confidence_interval", {})
        baseline_interval = baseline.get("confidence_interval", {})
        if (rate is not None and baseline_rate is not None and rate >= baseline_rate
                and interval.get("low") is not None and interval["low"] >= quality_floor):
            candidate["recommendation"] = "keep_shadow"
        elif (interval.get("high") is not None and baseline_interval.get("low") is not None
              and interval["high"] < baseline_interval["low"]):
            candidate["recommendation"] = "retire_candidate"
        else:
            candidate["recommendation"] = "collect_more_data"


def benchmark_report(project_root: str | Path = ".", mission_path: str | Path | None = None, *, config: BenchmarkConfig | None = None, code_ref: str = "") -> dict:
    """Measure available routing evidence or return an explicit gap report."""
    root = Path(project_root).resolve()
    source = Path(mission_path) if mission_path is not None else None
    config = config or BenchmarkConfig()
    config.validate()
    report = _base_report(root, source, code_ref, config)
    if source is None:
        report["gaps"] = [
            {"code": "no_replayable_missions", "detail": "The private QA ledger stores fingerprints, not sanitized task text, so it cannot be replayed."},
            {"code": "temporal_holdout_unavailable", "detail": "A dated sanitized mission set was not provided."},
            {"code": "verified_routing_feedback_below_minimum", "observed": report["evidence_inventory"]["verified_binary_router_feedback"], "required": config.min_train + config.min_holdout},
        ]
        return report
    try:
        missions = load_missions(source)
    except MissionValidationError as error:
        report["benchmark_status"] = "invalid_dataset"
        report["conclusion"] = "Reject the mission set and repair sanitization or provenance before benchmarking."
        report["gaps"] = [{"code": error.code, "detail": str(error)}]
        return report

    train, holdout, gaps = temporal_split(missions, config)
    dataset_classes = {item.dataset_class for item in missions}
    dataset_class = next(iter(dataset_classes)) if len(dataset_classes) == 1 else "mixed"
    blocking = bool(gaps) or dataset_class != "verified"
    if dataset_class != "verified":
        gaps.append({"code": "non_verified_dataset", "detail": "Fixture or mixed data can test the harness but cannot support a mechanism conclusion."})
    report["dataset"].update({
        "dataset_class": dataset_class,
        "missions": len(missions),
        "train": len(train),
        "holdout": len(holdout),
        "train_families": len({item.family_id for item in train}),
        "holdout_families": len({item.family_id for item in holdout}),
        "exact_task_leakage": any(gap["code"] == "exact_task_leakage" for gap in gaps),
        "task_family_leakage": any(gap["code"] == "task_family_leakage" for gap in gaps),
        "eligible_for_conclusions": not blocking,
    })
    report["gaps"] = gaps
    if any(gap["code"] in {"exact_task_leakage", "task_family_leakage", "temporal_boundary_not_strict"} for gap in gaps):
        report["benchmark_status"] = "rejected_for_leakage"
        report["conclusion"] = "Reject the split: temporal, exact-task, or task-family leakage would invalidate comparison."
        return report
    if not holdout or not train:
        return report

    deterministic, deterministic_rows = _evaluate("deterministic", holdout, _deterministic)
    knn_predict, temporary, setup_ms = _knn(train)
    try:
        knn, knn_rows = _evaluate("knn", holdout, knn_predict, setup_ms=setup_ms)
    finally:
        temporary.cleanup()
    micro, micro_rows = _evaluate("micro_nn", holdout, _micro_nn(config), calibration=True)
    report["routing_quality"] = {"deterministic": deterministic, "knn": knn, "micro_nn": micro}
    predictions = {"deterministic": deterministic_rows, "knn": knn_rows, "micro_nn": micro_rows}
    report["disagreement"] = {"status": "measured", "pairwise_rates": _pairwise(predictions)}
    report["benchmark_status"] = "measured_fixture" if blocking else "measured_verified_holdout"
    report["conclusion"] = (
        "Harness measured fixture behavior only; collect verified missions before ranking mechanisms."
        if blocking else
        "Verified holdout measured; recommendations remain shadow-only and cannot activate routing."
    )
    report["evidence_inventory"]["replayable_quality_missions"] = len(missions)
    report["evidence_inventory"]["binary_router_candidate"]["benchmark_eligible"] = not blocking
    _recommend(report, not blocking, config.quality_floor)
    return report


__all__ = [
    "BenchmarkConfig", "Mission", "MissionValidationError", "benchmark_report",
    "load_missions", "temporal_split",
]
