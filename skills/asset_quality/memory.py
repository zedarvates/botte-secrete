"""Verified, family-isolated quality memory for generated assets.

Hard integrity and licensing checks always run before the k-NN baseline.  The
baseline is shadow-only: it can explain a verdict but cannot publish, import,
or activate an asset.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA = "botte.asset-quality/v1"
FAMILIES = ("image", "texture", "mesh", "animation", "godot")
VERDICTS = ("FAIL", "UNCERTAIN", "PASS", "PASS_ROBUST")
MIN_NEIGHBORS = 3
MAX_ENTRIES = 5_000
MAX_BYTES = 8 * 1024 * 1024
MIN_SIMILARITY = 0.70

_VERDICT_SCORE = {"FAIL": 0.0, "UNCERTAIN": 0.4, "PASS": 0.8, "PASS_ROBUST": 1.0}
_COMMON_CHECKS = ("decodable", "license_verified", "manifest_verified")
_FAMILY_CHECKS = {
    "image": ("dimensions_valid",),
    "texture": ("dimensions_valid",),
    "mesh": ("finite_geometry", "nonempty_geometry"),
    "animation": ("valid_timeline",),
    "godot": ("importable",),
}
_FEATURES = {
    "image": ("aesthetic", "artifact_free", "composition", "prompt_alignment", "technical"),
    "texture": ("artifact_free", "prompt_alignment", "seamless", "technical", "tiling"),
    "mesh": ("manifold", "normals", "prompt_alignment", "scale", "topology", "uv"),
    "animation": ("continuity", "loop_quality", "prompt_alignment", "timing"),
    "godot": ("import_health", "performance", "prompt_alignment", "runtime_health"),
}
_VERIFIER_FAMILIES = {
    "benchmark", "ci", "deterministic", "harness", "human", "independent",
    "pytest", "replay", "schema", "tests",
}


@dataclass(frozen=True)
class AssetAdvice:
    status: str
    verdict: str
    reason: str
    family: str
    evidence_strength: float
    neighbor_count: int
    neighbors: list[dict]
    failed_checks: list[str]
    missing_checks: list[str]
    shadow_only: bool = True
    acted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".botte" / "asset-quality.jsonl"


def _family(value: object) -> str:
    family = str(value).strip().casefold()
    if family not in FAMILIES:
        raise ValueError(f"family must be one of: {', '.join(FAMILIES)}")
    return family


def _sha256(value: object) -> str:
    digest = str(value).strip().casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("sha256 must be a 64-character hexadecimal digest")
    return digest


def _size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("size_bytes must be a positive integer")
    return value


def _features(report: dict, family: str) -> list[float]:
    source = report.get("features")
    if not isinstance(source, dict):
        raise ValueError("features must be an object")
    expected = _FEATURES[family]
    if set(source) != set(expected):
        raise ValueError(f"features for {family} must be exactly: {', '.join(expected)}")
    values: list[float] = []
    for name in expected:
        value = source[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {name} must be numeric")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(f"feature {name} must be between 0 and 1")
        values.append(number)
    return values


def _checks(report: dict, family: str) -> tuple[list[str], list[str]]:
    source = report.get("checks")
    if not isinstance(source, dict):
        source = {}
    required = (*_COMMON_CHECKS, *_FAMILY_CHECKS[family])
    missing = [name for name in required if name not in source]
    invalid = [name for name in required if name in source and not isinstance(source[name], bool)]
    if invalid:
        raise ValueError(f"checks must be boolean: {', '.join(invalid)}")
    failed = [name for name in required if source.get(name) is False]
    return failed, missing


def _validate_report(report: object) -> tuple[dict, str, list[float], list[str], list[str]]:
    if not isinstance(report, dict):
        raise ValueError("asset report must be an object")
    family = _family(report.get("family"))
    digest = _sha256(report.get("sha256"))
    _size(report.get("size_bytes"))
    values = _features(report, family)
    failed, missing = _checks(report, family)
    clean = dict(report)
    clean["family"] = family
    clean["sha256"] = digest
    return clean, family, values, failed, missing


def _similarity(left: list[float], right: list[float]) -> float:
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))
    return max(0.0, 1.0 - distance / math.sqrt(len(left)))


def _load(project_root: str | Path) -> list[dict]:
    try:
        lines = _path(project_root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines[-MAX_ENTRIES:]:
        try:
            item = json.loads(line)
            family = _family(item.get("family"))
            if item.get("schema") != SCHEMA or item.get("verified") is not True:
                continue
            if item.get("verdict") not in VERDICTS or item.get("raw_asset_path_stored") is not False:
                continue
            values = item.get("features")
            if not isinstance(values, list) or len(values) != len(_FEATURES[family]):
                continue
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
                   for value in values):
                continue
            verifier = item.get("verified_by")
            if not isinstance(verifier, str) or not verifier:
                continue
            verifier_family = verifier.casefold().split(":", 1)[0].replace("-", "_")
            if verifier_family not in _VERIFIER_FAMILIES:
                continue
            _sha256(item.get("sha256"))
            _size(item.get("size_bytes"))
            records.append(item)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return records


def _support(records: Iterable[dict]) -> list[dict]:
    """Keep the latest label per family/hash so copies cannot create evidence."""
    latest: dict[tuple[str, str], dict] = {}
    for item in records:
        latest[(item["family"], item["sha256"])] = item
    return list(latest.values())


def _append(project_root: str | Path, record: dict) -> None:
    path = _path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > MAX_BYTES:
        lines = path.read_text(encoding="utf-8").splitlines()[-MAX_ENTRIES // 2:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def record_verified(
    report: dict,
    *,
    verdict: str,
    verified_by: str,
    project_root: str | Path = ".",
    evidence_refs: Iterable[str] = (),
) -> dict:
    """Record one externally verified asset result; never stores a local path."""
    clean, family, values, failed, missing = _validate_report(report)
    verdict = str(verdict).strip().upper().replace("-", "_")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of: {', '.join(VERDICTS)}")
    verifier = " ".join(str(verified_by).split())
    verifier_family = verifier.casefold().split(":", 1)[0].replace("-", "_")
    if not verifier or verifier_family not in _VERIFIER_FAMILIES:
        raise ValueError("verified_by must identify an external verifier")
    if failed and verdict != "FAIL":
        raise ValueError("a failed deterministic check can only be recorded as FAIL")
    if missing:
        raise ValueError("all deterministic checks are required before recording")
    refs = list(evidence_refs)
    if isinstance(evidence_refs, (str, bytes)) or len(refs) > 20:
        raise ValueError("evidence_refs must be a list of at most 20 strings")
    if any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in refs):
        raise ValueError("each evidence reference must be a non-empty string of at most 256 characters")
    now = time.time()
    record = {
        "schema": SCHEMA,
        "id": f"aq_{uuid.uuid4().hex[:12]}",
        "recorded_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "timestamp": now,
        "verified": True,
        "verified_by": verifier,
        "family": family,
        "sha256": clean["sha256"],
        "size_bytes": clean["size_bytes"],
        "feature_names": list(_FEATURES[family]),
        "features": values,
        "verdict": verdict,
        "quality_score": _VERDICT_SCORE[verdict],
        "evidence_refs": [ref.strip() for ref in refs],
        "raw_asset_path_stored": False,
    }
    _append(project_root, record)
    return record


def evaluate_asset(
    report: dict,
    *,
    project_root: str | Path = ".",
    k: int = 5,
    min_similarity: float = MIN_SIMILARITY,
) -> AssetAdvice:
    """Run deterministic gates, then return a family-local shadow verdict."""
    _, family, values, failed, missing = _validate_report(report)
    if failed:
        return AssetAdvice("rule_fail", "FAIL", "A mandatory deterministic check failed.",
                           family, 1.0, 0, [], failed, missing)
    if missing:
        return AssetAdvice("incomplete", "UNCERTAIN", "Mandatory checks are missing.",
                           family, 0.0, 0, [], failed, missing)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 50:
        raise ValueError("k must be between 1 and 50")
    if isinstance(min_similarity, bool) or not isinstance(min_similarity, (int, float)) \
            or not 0.0 <= float(min_similarity) <= 1.0:
        raise ValueError("min_similarity must be between 0 and 1")
    family_records = [item for item in _support(_load(project_root)) if item["family"] == family]
    scored = sorted(
        ((_similarity(values, item["features"]), item) for item in family_records),
        key=lambda pair: pair[0], reverse=True,
    )
    nearest = [pair for pair in scored if pair[0] >= float(min_similarity)][:k]
    neighbors = [{"id": item["id"], "similarity": round(sim, 4),
                  "verdict": item["verdict"], "verified_by": item["verified_by"]}
                 for sim, item in nearest]
    if len(nearest) < MIN_NEIGHBORS:
        return AssetAdvice("abstain", "UNCERTAIN",
                           "Too few similar verified assets in this family.", family,
                           0.0, len(nearest), neighbors, [], [])
    weight = sum(max(sim, 0.001) for sim, _ in nearest)
    score = sum(max(sim, 0.001) * item["quality_score"] for sim, item in nearest) / weight
    verdict = "FAIL" if score < 0.25 else "UNCERTAIN" if score < 0.60 else \
        "PASS" if score < 0.90 else "PASS_ROBUST"
    strength = min(0.95, (sum(sim for sim, _ in nearest) / len(nearest)) * len(nearest) / k)
    return AssetAdvice("suggest", verdict,
                       f"Weighted verdict from {len(nearest)} verified {family} neighbor(s).",
                       family, round(strength, 4), len(nearest), neighbors, [], [])


def quality_status(project_root: str | Path = ".") -> dict:
    recorded = _load(project_root)
    records = _support(recorded)
    counts = Counter(item["family"] for item in records)
    return {
        "schema": "botte.asset-quality-status/v1",
        "mode": "shadow",
        "recorded_outcomes": len(recorded),
        "verified_assets": len(records),
        "by_family": {family: counts.get(family, 0) for family in FAMILIES},
        "families_ready": [family for family in FAMILIES if counts.get(family, 0) >= MIN_NEIGHBORS],
        "activation_allowed": False,
        "next_action": "Record externally verified assets for each family with fewer than 3 examples.",
    }
