"""Bounded execution outcomes that promote only verified evidence to QA memory.

Integrations emit privacy-safe lifecycle facts here.  Every envelope is useful
for status/replay, but only a verdict backed by an allowed external verifier and
at least one evidence reference becomes a ``botte.quality-trajectory/v1`` row.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from skills.events import log_event
from skills.trajectory.quality import (
    RISKS,
    ROUTES,
    VERDICTS,
    fingerprint_task,
    load_verified,
    record_verified,
    trusted_verifier,
)

SCHEMA = "botte.quality-outcome/v1"
EVENT_KIND = "qa_outcome"
STATUSES = (
    "PARTIAL", "FAIL", "UNCERTAIN", "PASS", "PASS_ROBUST",
    "ABSTAINED", "ESCALATED", "APPROVAL_REQUIRED",
)
REVIEW_VERDICTS = ("ACCEPT", "REWORK", "BLOCKED")
MAX_ENTRIES = 5_000
MAX_BYTES = 8 * 1024 * 1024
_OUTCOME_ID = re.compile(r"^qo_[0-9a-f]{16}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def _outcome_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".botte" / "quality-outcomes.jsonl"


def _text(value: object, *, field: str, maximum: int, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def _strings(values: Iterable[str], *, field: str, maximum: int, limit: int) -> list[str]:
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError(f"{field} must be a list of strings")
    items = list(values)
    if len(items) > limit:
        raise ValueError(f"{field} must contain at most {limit} items")
    return [_text(item, field=field[:-1], maximum=maximum, required=True) for item in items]


def _metric(value: float | int | None, *, field: str, integer: bool = False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if integer and not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return value


def _versions(values: Mapping[str, str] | None) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, Mapping) or len(values) > 20:
        raise ValueError("tool_versions must be an object with at most 20 entries")
    return {
        _text(key, field="tool_version key", maximum=64, required=True):
        _text(value, field="tool_version value", maximum=128, required=True)
        for key, value in sorted(values.items())
    }


def _git_oid(value: object, *, field: str) -> str:
    cleaned = _text(value, field=field, maximum=64)
    if cleaned and (
        len(cleaned) not in (40, 64)
        or any(char not in "0123456789abcdef" for char in cleaned)
    ):
        raise ValueError(f"{field} must be a lowercase Git object ID")
    return cleaned


def _sha256(value: object, *, field: str) -> str:
    cleaned = _text(value, field=field, maximum=64)
    if cleaned and not _FINGERPRINT.fullmatch(cleaned):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return cleaned


def _workspace_lease(value: Mapping | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("workspace_lease must be an object")
    allowed = {
        "lease_id", "worker_id", "state", "base_sha", "head_sha",
        "expires_at", "workspace_fingerprint",
    }
    if set(value) != allowed:
        raise ValueError("workspace_lease must contain only privacy-safe contract fields")
    state = _text(value["state"], field="workspace_lease.state", maximum=16, required=True)
    if state not in ("ACTIVE", "RELEASED", "QUARANTINED", "EXPIRED"):
        raise ValueError("workspace_lease.state is unsupported")
    return {
        "lease_id": _text(
            value["lease_id"], field="workspace_lease.lease_id", maximum=128, required=True
        ),
        "worker_id": _text(
            value["worker_id"], field="workspace_lease.worker_id", maximum=128, required=True
        ),
        "state": state,
        "base_sha": _git_oid(value["base_sha"], field="workspace_lease.base_sha"),
        "head_sha": _git_oid(value["head_sha"], field="workspace_lease.head_sha"),
        "expires_at": _text(
            value["expires_at"], field="workspace_lease.expires_at", maximum=64, required=True
        ),
        "workspace_fingerprint": _sha256(
            value["workspace_fingerprint"], field="workspace_lease.workspace_fingerprint"
        ),
    }


def _checks(values: Iterable[Mapping]) -> list[dict]:
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("checks must be a list")
    items = list(values)
    if len(items) > 100:
        raise ValueError("checks must contain at most 100 items")
    normalized = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {
            "name", "status", "evidence_ref"
        }:
            raise ValueError("each check requires name, status and evidence_ref")
        status = _text(item["status"], field="check.status", maximum=16, required=True)
        if status not in ("PASS", "FAIL", "UNCERTAIN", "SKIPPED"):
            raise ValueError("check.status is unsupported")
        normalized.append({
            "name": _text(item["name"], field="check.name", maximum=128, required=True),
            "status": status,
            "evidence_ref": _text(
                item["evidence_ref"], field="check.evidence_ref", maximum=256
            ),
        })
    return normalized


def _artifacts(values: Iterable[Mapping]) -> list[dict]:
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("artifacts must be a list")
    items = list(values)
    if len(items) > 100:
        raise ValueError("artifacts must contain at most 100 items")
    normalized = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"kind", "ref", "sha256"}:
            raise ValueError("each artifact requires kind, ref and sha256")
        reference = _text(item["ref"], field="artifact.ref", maximum=256, required=True)
        if reference.startswith(("/", "~", "\\")) or (
            len(reference) >= 3 and reference[1:3] in (":/", ":\\")
        ):
            raise ValueError("artifact.ref must not expose an absolute machine path")
        normalized.append({
            "kind": _text(item["kind"], field="artifact.kind", maximum=64, required=True),
            "ref": reference,
            "sha256": _sha256(item["sha256"], field="artifact.sha256"),
        })
    return normalized


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()
            keep = min(MAX_ENTRIES, max(1, len(lines) // 2))
            path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _valid(item: object) -> bool:
    if not isinstance(item, dict) or item.get("schema") != SCHEMA:
        return False
    if item.get("raw_task_stored") is not False:
        return False
    if any(field in item for field in ("task", "prompt", "input_text", "answer")):
        return False
    outcome_id = item.get("id")
    if not isinstance(outcome_id, str) or not _OUTCOME_ID.fullmatch(outcome_id):
        return False
    if item.get("route") not in ROUTES or item.get("status") not in STATUSES:
        return False
    if item.get("verdict") not in (*VERDICTS, None):
        return False
    fingerprint = item.get("task_fingerprint")
    return isinstance(fingerprint, str) and bool(_FINGERPRINT.fullmatch(fingerprint))


def load_outcomes(project_root: str | Path = ".", limit: int = MAX_ENTRIES) -> list[dict]:
    """Load valid private outcome envelopes oldest-first."""
    try:
        lines = _outcome_path(project_root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if _valid(item):
            records.append(item)
    return records


def emit_outcome(
    task: str,
    *,
    route: str,
    status: str,
    project_root: str | Path = ".",
    execution_id: str = "",
    source: str = "",
    task_type: str = "",
    tags: Iterable[str] = (),
    verdict: str | None = None,
    verified_by: str = "",
    evidence_refs: Iterable[str] = (),
    quality_score: float | None = None,
    risk: str = "standard",
    permission_profile: str = "",
    model: str = "",
    harness: str = "",
    tool_versions: Mapping[str, str] | None = None,
    duration_ms: float | None = None,
    cost_usd: float | None = None,
    tokens: int | None = None,
    memory_mb: float | None = None,
    energy_wh: float | None = None,
    acted: bool = False,
    abstained: bool = False,
    escalated: bool = False,
    approval_required: bool = False,
    mission_id: str = "",
    attempt_id: str = "",
    worker_id: str = "",
    workspace_lease: Mapping | None = None,
    repository_ref: str = "",
    base_sha: str = "",
    head_sha: str = "",
    dirty_tree_sha256: str = "",
    check_command_sha256: str = "",
    checks: Iterable[Mapping] = (),
    artifacts: Iterable[Mapping] = (),
    uncertainties: Iterable[str] = (),
    review_verdict: str | None = None,
    next_safe_action: str = "",
) -> dict:
    """Emit one idempotent envelope and optionally promote its verified verdict.

    ``execution_id`` is hashed rather than stored. Replaying the same execution
    and outcome content returns the prior envelope and cannot add another label.
    """
    route = str(route).strip().casefold()
    status = str(status).strip().upper().replace("-", "_")
    risk = str(risk).strip().casefold()
    if route not in ROUTES:
        raise ValueError(f"route must be one of: {', '.join(ROUTES)}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if risk not in RISKS:
        raise ValueError(f"risk must be one of: {', '.join(RISKS)}")
    if verdict is None and status in VERDICTS:
        verdict = status
    if verdict is not None:
        verdict = str(verdict).strip().upper().replace("-", "_")
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of: {', '.join(VERDICTS)}")

    normal_tags = sorted({
        tag.casefold() for tag in _strings(tags, field="tags", maximum=64, limit=50)
    })
    evidence = _strings(evidence_refs, field="evidence_refs", maximum=256, limit=20)
    verifier = _text(verified_by, field="verified_by", maximum=128)
    task_type = _text(task_type, field="task_type", maximum=64)
    task_fingerprint = fingerprint_task(task, task_type, normal_tags)
    source = _text(source, field="source", maximum=64)
    harness = _text(harness, field="harness", maximum=128)
    model = _text(model, field="model", maximum=128)
    permission_profile = _text(
        permission_profile, field="permission_profile", maximum=64
    )
    versions = _versions(tool_versions)
    mission_id = _text(mission_id, field="mission_id", maximum=128)
    attempt_id = _text(attempt_id, field="attempt_id", maximum=128)
    worker_id = _text(worker_id, field="worker_id", maximum=128)
    lease = _workspace_lease(workspace_lease)
    repository_ref = _text(repository_ref, field="repository_ref", maximum=256)
    base_sha = _git_oid(base_sha, field="base_sha")
    head_sha = _git_oid(head_sha, field="head_sha")
    dirty_tree_sha256 = _sha256(dirty_tree_sha256, field="dirty_tree_sha256")
    check_command_sha256 = _sha256(
        check_command_sha256, field="check_command_sha256"
    )
    normalized_checks = _checks(checks)
    normalized_artifacts = _artifacts(artifacts)
    normalized_uncertainties = _strings(
        uncertainties, field="uncertainties", maximum=512, limit=100
    )
    if review_verdict is not None:
        review_verdict = str(review_verdict).strip().upper()
        if review_verdict not in REVIEW_VERDICTS:
            raise ValueError(f"review_verdict must be one of: {', '.join(REVIEW_VERDICTS)}")
        verifier_family = verifier.partition(":")[0].casefold()
        if verifier_family not in {"human", "independent"}:
            raise ValueError("review_verdict requires an independent or human verifier")
    next_safe_action = _text(
        next_safe_action, field="next_safe_action", maximum=512
    )
    binding_values = (mission_id, attempt_id, worker_id)
    if any(binding_values) and not all(binding_values):
        raise ValueError("mission_id, attempt_id and worker_id must be supplied together")
    if lease and lease["worker_id"] != worker_id:
        raise ValueError("workspace_lease.worker_id must match worker_id")
    if lease and base_sha and lease["base_sha"] != base_sha:
        raise ValueError("workspace_lease.base_sha must match base_sha")
    if lease and head_sha and lease["head_sha"] != head_sha:
        raise ValueError("workspace_lease.head_sha must match head_sha")
    duration_ms = _metric(duration_ms, field="duration_ms")
    cost_usd = _metric(cost_usd, field="cost_usd")
    tokens = _metric(tokens, field="tokens", integer=True)
    memory_mb = _metric(memory_mb, field="memory_mb")
    energy_wh = _metric(energy_wh, field="energy_wh")
    if quality_score is not None:
        quality_score = _metric(quality_score, field="quality_score")
        if float(quality_score) > 1:
            raise ValueError("quality_score must be between 0 and 1")

    execution_id = _text(execution_id, field="execution_id", maximum=256)
    execution_basis = execution_id or json.dumps({
        "task_fingerprint": task_fingerprint,
        "route": route,
        "source": source,
        "harness": harness,
    }, sort_keys=True, separators=(",", ":"))
    execution_fingerprint = hashlib.sha256(execution_basis.encode("utf-8")).hexdigest()

    can_promote = bool(verdict and evidence and trusted_verifier(verifier))
    if can_promote:
        verification_state = "verified"
    elif verdict and (verifier or evidence):
        verification_state = "rejected"
    else:
        verification_state = "unverified"

    identity = json.dumps({
        "execution_fingerprint": execution_fingerprint,
        "route": route,
        "status": status,
        "verdict": verdict,
        "verified_by": verifier,
        "evidence_refs": evidence,
        "source": source,
        "harness": harness,
        "model": model,
        "mission_id": mission_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "workspace_lease": lease,
        "repository_ref": repository_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "dirty_tree_sha256": dirty_tree_sha256,
        "check_command_sha256": check_command_sha256,
        "review_verdict": review_verdict,
    }, sort_keys=True, separators=(",", ":"))
    outcome_id = "qo_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    existing = next((item for item in load_outcomes(project_root)
                     if item.get("id") == outcome_id), None)
    if existing is not None:
        return {"envelope": existing, "trajectory": next(
            (row for row in load_verified(project_root)
             if row.get("outcome_id") == outcome_id), None
        ), "deduplicated": True}

    trajectory = None
    if can_promote:
        trajectory = record_verified(
            task,
            project_root=project_root,
            route=route,
            verdict=verdict or "UNCERTAIN",
            verified_by=verifier,
            task_type=task_type,
            tags=normal_tags,
            quality_score=quality_score,
            risk=risk,
            model=model,
            harness=harness,
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            tokens=tokens,
            evidence_refs=evidence,
            outcome_id=outcome_id,
        )

    now = time.time()
    envelope = {
        "schema": SCHEMA,
        "schema_version": 1,
        "id": outcome_id,
        "recorded_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "timestamp": now,
        "execution_fingerprint": execution_fingerprint,
        "source": source,
        "task_fingerprint": task_fingerprint,
        "task_type": task_type,
        "tags": normal_tags,
        "route": route,
        "status": status,
        "verdict": verdict,
        "verification_state": verification_state,
        "verified": can_promote,
        "verified_by": verifier if can_promote else "",
        "evidence_refs": evidence,
        "risk": risk,
        "permission_profile": permission_profile,
        "model": model,
        "harness": harness,
        "tool_versions": versions,
        "mission_id": mission_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "workspace_lease": lease,
        "repository_ref": repository_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "dirty_tree_sha256": dirty_tree_sha256,
        "check_command_sha256": check_command_sha256,
        "checks": normalized_checks,
        "artifacts": normalized_artifacts,
        "uncertainties": normalized_uncertainties,
        "review_verdict": review_verdict,
        "next_safe_action": next_safe_action,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
        "tokens": tokens,
        "memory_mb": memory_mb,
        "energy_wh": energy_wh,
        "acted": bool(acted),
        "abstained": bool(abstained or status == "ABSTAINED"),
        "escalated": bool(escalated or status == "ESCALATED"),
        "approval_required": bool(
            approval_required or status == "APPROVAL_REQUIRED"
        ),
        "shadow_only": True,
        "activation_allowed": False,
        "raw_task_stored": False,
        "trajectory_id": trajectory.get("id") if trajectory else None,
    }
    _append(_outcome_path(project_root), envelope)
    log_event(
        EVENT_KIND,
        project_root=project_root,
        outcome_id=outcome_id,
        execution_fingerprint=execution_fingerprint,
        source=source,
        route=route,
        status=status,
        verdict=verdict,
        verification_state=verification_state,
        evidence_count=len(evidence),
        acted=envelope["acted"],
        abstained=envelope["abstained"],
        escalated=envelope["escalated"],
        approval_required=envelope["approval_required"],
        trajectory_id=envelope["trajectory_id"],
        shadow_only=True,
    )
    return {"envelope": envelope, "trajectory": trajectory, "deduplicated": False}


__all__ = ["EVENT_KIND", "SCHEMA", "STATUSES", "emit_outcome", "load_outcomes"]
