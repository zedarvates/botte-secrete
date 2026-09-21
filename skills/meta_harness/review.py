"""Independent Gauntlet review and best-known-green checkpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from skills.atomic_json import write_json
from skills.run_contract import (
    REVIEW_VERDICTS,
    contract_fingerprint,
    validate_handoff,
    validate_mission,
)


REVIEW_SCHEMA = "botte.review/v1"
CHECKPOINT_SCHEMA = "botte.checkpoints/v1"


class ReviewError(ValueError):
    """Review input is malformed or violates independent-review boundaries."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value, *, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{field} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise ReviewError(f"{field} exceeds {maximum} characters")
    return cleaned


def _review_lease(value: Mapping, reviewer_id: str) -> dict:
    if not isinstance(value, Mapping):
        raise ReviewError("review_workspace_lease must be an object")
    required = {
        "lease_id", "worker_id", "state", "base_sha", "head_sha",
        "expires_at", "workspace_fingerprint",
    }
    if set(value) != required:
        raise ReviewError("review_workspace_lease fields do not match the lease contract")
    lease = dict(value)
    if lease["worker_id"] != reviewer_id:
        raise ReviewError("review lease must belong to reviewer_id")
    if lease["state"] != "ACTIVE":
        raise ReviewError("review lease must be ACTIVE")
    fingerprint = lease["workspace_fingerprint"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ReviewError("review workspace fingerprint is invalid")
    return lease


def _checks(values: Iterable[Mapping]) -> list[dict]:
    items = list(values)
    if not items or len(items) > 100:
        raise ReviewError("replayed_checks must contain 1-100 checks")
    normalized = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {
            "name", "status", "evidence_ref"
        }:
            raise ReviewError("each replayed check requires name, status and evidence_ref")
        status = _text(item["status"], field="check.status", maximum=16).upper()
        if status not in ("PASS", "FAIL", "UNCERTAIN", "SKIPPED"):
            raise ReviewError("unsupported replayed check status")
        normalized.append(
            {
                "name": _text(item["name"], field="check.name", maximum=128),
                "status": status,
                "evidence_ref": _text(
                    item["evidence_ref"], field="check.evidence_ref", maximum=256
                ),
            }
        )
    return normalized


def review_handoff(
    mission: Mapping,
    handoff: Mapping,
    *,
    reviewer_id: str,
    review_workspace_lease: Mapping,
    replayed_checks: Iterable[Mapping],
    previous_failure_refs: Iterable[str] = (),
    closed_failure_refs: Iterable[str] = (),
    created_at: str | None = None,
) -> dict:
    """Review a handoff from a distinct worker/workspace.

    The reviewer never mutates the author handoff. It returns only ACCEPT,
    REWORK or BLOCKED and binds that verdict to the reviewed handoff digest.
    """
    normalized_mission = validate_mission(mission)
    normalized_handoff = validate_handoff(handoff)
    reviewer = _text(reviewer_id, field="reviewer_id", maximum=128)
    if normalized_handoff["mission_id"] != normalized_mission["mission_id"]:
        raise ReviewError("mission and handoff identifiers do not match")
    if reviewer == normalized_handoff["worker_id"]:
        raise ReviewError("author and independent reviewer must be different workers")
    review_lease = _review_lease(review_workspace_lease, reviewer)
    author_fingerprint = normalized_handoff["workspace_lease"]["workspace_fingerprint"]
    if review_lease["workspace_fingerprint"] == author_fingerprint:
        raise ReviewError("review must run in a distinct workspace")

    checks = _checks(replayed_checks)
    previous = sorted({_text(item, field="previous_failure_ref") for item in previous_failure_refs})
    closed = sorted({_text(item, field="closed_failure_ref") for item in closed_failure_refs})
    reasons: list[str] = []
    verdict = "ACCEPT"

    missing_required = sorted(
        set(normalized_mission["required_evidence"])
        - set(normalized_handoff["evidence_refs"])
    )
    if normalized_handoff["status"] != "READY_FOR_REVIEW":
        verdict = "BLOCKED"
        reasons.append("handoff_not_ready_for_review")
    if normalized_handoff["review_verdict"] is not None:
        verdict = "BLOCKED"
        reasons.append("handoff_already_contains_review_verdict")
    if missing_required:
        verdict = "BLOCKED"
        reasons.append("missing_required_evidence:" + ",".join(missing_required))
    if any(not artifact["sha256"] for artifact in normalized_handoff["artifacts"]):
        verdict = "BLOCKED"
        reasons.append("artifact_without_digest")
    if normalized_handoff["approval_required"]:
        verdict = "BLOCKED"
        reasons.append("human_approval_required")
    if (
        normalized_mission["risk"] in ("R3", "R4")
        and not normalized_mission.get("owner_approval_ref")
    ):
        verdict = "BLOCKED"
        reasons.append("owner_review_pending")

    statuses = {item["status"] for item in checks}
    if "FAIL" in statuses:
        verdict = "REWORK"
        reasons.append("independent_replay_failed")
    elif statuses & {"UNCERTAIN", "SKIPPED"}:
        verdict = "BLOCKED"
        reasons.append("independent_replay_incomplete")
    if normalized_handoff["uncertainties"] and verdict == "ACCEPT":
        verdict = "REWORK"
        reasons.append("unresolved_uncertainty")

    not_closed = sorted(set(previous) - set(closed))
    if not_closed:
        verdict = "REWORK"
        reasons.append("prior_failure_not_closed:" + ",".join(not_closed))

    if verdict not in REVIEW_VERDICTS:
        raise ReviewError("internal unsupported review verdict")
    if not reasons:
        reasons.append("independent_replay_passed")

    next_actions = {
        "ACCEPT": "Preserve this SHA as best-known-green; await owner-only transitions.",
        "REWORK": "Revise only the named failing proofs, then request a fresh review.",
        "BLOCKED": "Resolve the missing evidence or approval before another review.",
    }
    evidence_refs = sorted(
        {item["evidence_ref"] for item in checks}
        | set(normalized_handoff["evidence_refs"])
    )
    packet = {
        "schema": REVIEW_SCHEMA,
        "mission_id": normalized_mission["mission_id"],
        "attempt_id": normalized_handoff["attempt_id"],
        "reviewer_id": reviewer,
        "created_at": created_at or _now(),
        "reviewed_handoff_sha256": normalized_handoff["handoff_sha256"],
        "author_workspace_fingerprint": author_fingerprint,
        "review_workspace_fingerprint": review_lease["workspace_fingerprint"],
        "head_sha": normalized_handoff["workspace_lease"]["head_sha"],
        "verdict": verdict,
        "reasons": reasons,
        "replayed_checks": checks,
        "evidence_refs": evidence_refs,
        "closed_failure_refs": closed,
        "approval_required": any(
            reason in {"human_approval_required", "owner_review_pending"}
            for reason in reasons
        ),
        "next_safe_action": next_actions[verdict],
    }
    packet["review_sha256"] = contract_fingerprint(packet)
    return packet


class CheckpointRegistry:
    """Keep revision limits and a best-known-green SHA in private local state."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.storage = self.project_root / ".botte-cache" / "checkpoints"

    def _path(self, mission_id: str) -> Path:
        digest = hashlib.sha256(mission_id.encode("utf-8")).hexdigest()[:24]
        return self.storage / f"mission-{digest}.json"

    def _empty(self, mission_id: str) -> dict:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "mission_id": mission_id,
            "attempts": [],
            "best_known_green": None,
            "last_review": None,
        }

    def load(self, mission_id: str) -> dict:
        path = self._path(mission_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            return self._empty(mission_id)
        except json.JSONDecodeError as exc:
            raise ReviewError("checkpoint registry is not valid JSON") from exc
        if payload.get("schema") != CHECKPOINT_SCHEMA or payload.get("mission_id") != mission_id:
            raise ReviewError("checkpoint registry contract mismatch")
        return payload

    def register_attempt(
        self,
        mission: Mapping,
        *,
        attempt_id: str,
        addressed_failure_refs: Iterable[str] = (),
    ) -> dict:
        normalized = validate_mission(mission)
        attempt = _text(attempt_id, field="attempt_id", maximum=128)
        addressed = sorted(
            {_text(item, field="addressed_failure_ref") for item in addressed_failure_refs}
        )
        state = self.load(normalized["mission_id"])
        existing = next(
            (item for item in state["attempts"] if item["attempt_id"] == attempt), None
        )
        if existing is not None:
            if existing["addressed_failure_refs"] != addressed:
                raise ReviewError("attempt replay changed its addressed failure set")
            return state
        if state["attempts"] and not addressed:
            raise ReviewError("a revision must name the failing proof it addresses")
        maximum = normalized["budgets"]["max_revisions"]
        for failure_ref in addressed:
            prior = sum(
                failure_ref in item["addressed_failure_refs"]
                for item in state["attempts"]
            )
            if prior >= maximum:
                raise ReviewError(
                    f"revision budget exhausted for failing proof: {failure_ref}"
                )
        state["attempts"].append(
            {
                "attempt_id": attempt,
                "addressed_failure_refs": addressed,
                "registered_at": _now(),
            }
        )
        write_json(self._path(normalized["mission_id"]), state)
        return state

    def record_review(self, review: Mapping) -> dict:
        if not isinstance(review, Mapping) or review.get("schema") != REVIEW_SCHEMA:
            raise ReviewError("review packet has an unsupported schema")
        packet = dict(review)
        digest = packet.pop("review_sha256", None)
        if digest != contract_fingerprint(packet):
            raise ReviewError("review packet fingerprint mismatch")
        mission_id = _text(review.get("mission_id"), field="mission_id", maximum=128)
        state = self.load(mission_id)
        state["last_review"] = {
            "attempt_id": review.get("attempt_id"),
            "verdict": review.get("verdict"),
            "review_sha256": digest,
        }
        if review.get("verdict") == "ACCEPT":
            state["best_known_green"] = {
                "attempt_id": review.get("attempt_id"),
                "head_sha": review.get("head_sha"),
                "review_sha256": digest,
                "recorded_at": _now(),
            }
        write_json(self._path(mission_id), state)
        return state


__all__ = [
    "CHECKPOINT_SCHEMA",
    "REVIEW_SCHEMA",
    "CheckpointRegistry",
    "ReviewError",
    "review_handoff",
]
