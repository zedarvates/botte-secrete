"""Deterministic mission, context-manifest and handoff contracts.

The module intentionally uses no JSON-schema runtime dependency. The JSON
schemas document the wire format; these validators enforce the operational
invariants that a structural schema cannot express.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


MISSION_SCHEMA = "botte.mission/v1"
CONTEXT_SCHEMA = "botte.context-manifest/v1"
HANDOFF_SCHEMA = "botte.handoff/v1"

AUTHORITY_TIERS = ("SIMULATE", "SHADOW", "ACT")
RISK_LEVELS = ("R0", "R1", "R2", "R3", "R4")
PRIVACY_LEVELS = ("PUBLIC", "PRIVATE", "CONFIDENTIAL")
HANDOFF_STATUSES = (
    "PARTIAL",
    "FAIL",
    "UNCERTAIN",
    "READY_FOR_REVIEW",
    "APPROVAL_REQUIRED",
)
REVIEW_VERDICTS = ("ACCEPT", "REWORK", "BLOCKED")
CHECK_STATUSES = ("PASS", "FAIL", "UNCERTAIN", "SKIPPED")
LEASE_STATES = ("ACTIVE", "RELEASED", "QUARANTINED", "EXPIRED")

CORE_FORBIDDEN_ACTIONS = frozenset(
    {"merge", "deploy", "release", "secrets", "payments"}
)

_MISSION_FIELDS = frozenset(
    {
        "schema",
        "mission_id",
        "objective",
        "scope",
        "forbidden_actions",
        "authority",
        "risk",
        "privacy",
        "capabilities",
        "budgets",
        "required_evidence",
        "approval_gates",
        "rollback",
        "context",
        "owner_approval_ref",
    }
)

_HANDOFF_FIELDS = frozenset(
    {
        "schema",
        "mission_id",
        "attempt_id",
        "worker_id",
        "created_at",
        "status",
        "workspace_lease",
        "checks",
        "evidence_refs",
        "artifacts",
        "uncertainties",
        "approval_required",
        "review_verdict",
        "next_safe_action",
        "safety_rules_pinned",
        "raw_context_stored",
        "handoff_sha256",
    }
)


class ContractError(ValueError):
    """A contract is structurally invalid or violates a safety invariant."""


def _canonical(payload: Mapping) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def contract_fingerprint(payload: Mapping) -> str:
    """Return a stable SHA-256 over canonical JSON."""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_time(value, *, field: str) -> str:
    text = _text(value, field=field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return text


def _mapping(value, *, field: str) -> dict:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field} must be an object")
    return dict(value)


def _text(value, *, field: str, maximum: int = 256, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a string")
    text = value.strip()
    if required and not text:
        raise ContractError(f"{field} must not be empty")
    if len(text) > maximum:
        raise ContractError(f"{field} exceeds {maximum} characters")
    return text


def _strings(
    value,
    *,
    field: str,
    maximum: int = 256,
    limit: int = 100,
) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise ContractError(f"{field} must be an array with at most {limit} items")
    result = [_text(item, field=f"{field}[]", maximum=maximum) for item in value]
    if len(set(result)) != len(result):
        raise ContractError(f"{field} must not contain duplicates")
    return result


def _relative_path(value: str, *, field: str) -> str:
    raw = _text(value, field=field, maximum=512).replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or raw.startswith("~"):
        raise ContractError(f"{field} must be a repository-relative path")
    if raw in ("", "."):
        raise ContractError(f"{field} must identify a file")
    return path.as_posix()


def _paths(value, *, field: str, limit: int = 200) -> list[str]:
    return [
        _relative_path(item, field=f"{field}[]")
        for item in _strings(value, field=field, maximum=512, limit=limit)
    ]


def _positive_int(value, *, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{field} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise ContractError(f"{field} must be >= {minimum}")
    return value


def _non_negative_number(value, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ContractError(f"{field} must be a non-negative number")
    return float(value)


def _reject_unknown(payload: Mapping, allowed: frozenset[str], *, field: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ContractError(f"{field} contains unknown fields: {', '.join(unknown)}")


def validate_mission(payload: Mapping) -> dict:
    """Validate and normalize a ``botte.mission/v1`` contract."""
    mission = _mapping(payload, field="mission")
    _reject_unknown(mission, _MISSION_FIELDS, field="mission")
    required = _MISSION_FIELDS - {"owner_approval_ref"}
    missing = sorted(required - set(mission))
    if missing:
        raise ContractError(f"mission is missing fields: {', '.join(missing)}")
    if mission.get("schema") != MISSION_SCHEMA:
        raise ContractError(f"schema must be {MISSION_SCHEMA}")

    mission_id = _text(mission["mission_id"], field="mission_id", maximum=128)
    if not all(ch.isalnum() or ch in "._:/-" for ch in mission_id):
        raise ContractError("mission_id contains unsupported characters")
    objective = _text(mission["objective"], field="objective", maximum=2000)

    scope = _mapping(mission["scope"], field="scope")
    _reject_unknown(scope, frozenset({"include", "exclude"}), field="scope")
    if set(scope) != {"include", "exclude"}:
        raise ContractError("scope requires include and exclude")
    include = _paths(scope["include"], field="scope.include")
    exclude = _paths(scope["exclude"], field="scope.exclude")
    if not include:
        raise ContractError("scope.include must not be empty")

    forbidden = _strings(
        mission["forbidden_actions"], field="forbidden_actions", maximum=64, limit=50
    )
    absent = sorted(CORE_FORBIDDEN_ACTIONS - set(forbidden))
    if absent:
        raise ContractError(
            "forbidden_actions must retain v1 owner-only actions: " + ", ".join(absent)
        )

    authority = _text(mission["authority"], field="authority", maximum=16)
    if authority not in AUTHORITY_TIERS:
        raise ContractError(f"authority must be one of {AUTHORITY_TIERS}")
    risk = _text(mission["risk"], field="risk", maximum=2)
    if risk not in RISK_LEVELS:
        raise ContractError(f"risk must be one of {RISK_LEVELS}")
    privacy = _text(mission["privacy"], field="privacy", maximum=16)
    if privacy not in PRIVACY_LEVELS:
        raise ContractError(f"privacy must be one of {PRIVACY_LEVELS}")

    capabilities = _strings(
        mission["capabilities"], field="capabilities", maximum=64, limit=50
    )
    evidence = _strings(
        mission["required_evidence"], field="required_evidence", maximum=128, limit=50
    )
    if not evidence:
        raise ContractError("required_evidence must not be empty")
    gates = _strings(
        mission["approval_gates"], field="approval_gates", maximum=128, limit=50
    )
    if risk in ("R3", "R4") and "owner-review" not in gates:
        raise ContractError("R3/R4 missions require the owner-review approval gate")

    budgets = _mapping(mission["budgets"], field="budgets")
    allowed_budgets = frozenset(
        {
            "max_iterations",
            "max_tool_calls",
            "max_wall_seconds",
            "max_tokens",
            "max_cost_usd",
            "max_revisions",
        }
    )
    _reject_unknown(budgets, allowed_budgets, field="budgets")
    missing_budgets = sorted(
        {"max_iterations", "max_tool_calls", "max_wall_seconds", "max_revisions"}
        - set(budgets)
    )
    if missing_budgets:
        raise ContractError(f"budgets is missing fields: {', '.join(missing_budgets)}")
    normalized_budgets = {
        "max_iterations": _positive_int(
            budgets["max_iterations"], field="budgets.max_iterations"
        ),
        "max_tool_calls": _positive_int(
            budgets["max_tool_calls"], field="budgets.max_tool_calls", allow_zero=True
        ),
        "max_wall_seconds": _positive_int(
            budgets["max_wall_seconds"], field="budgets.max_wall_seconds"
        ),
        "max_revisions": _positive_int(
            budgets["max_revisions"], field="budgets.max_revisions"
        ),
    }
    if "max_tokens" in budgets:
        normalized_budgets["max_tokens"] = _positive_int(
            budgets["max_tokens"], field="budgets.max_tokens", allow_zero=True
        )
    if "max_cost_usd" in budgets:
        normalized_budgets["max_cost_usd"] = _non_negative_number(
            budgets["max_cost_usd"], field="budgets.max_cost_usd"
        )

    rollback = _mapping(mission["rollback"], field="rollback")
    _reject_unknown(rollback, frozenset({"required", "snapshot_ref"}), field="rollback")
    if not isinstance(rollback.get("required"), bool):
        raise ContractError("rollback.required must be a boolean")
    snapshot_ref = _text(
        rollback.get("snapshot_ref", ""),
        field="rollback.snapshot_ref",
        maximum=256,
        required=False,
    )

    owner_ref = _text(
        mission.get("owner_approval_ref", ""),
        field="owner_approval_ref",
        maximum=256,
        required=False,
    )
    if authority == "ACT" and not owner_ref:
        raise ContractError("ACT requires an opaque owner_approval_ref")
    if authority == "ACT" and (not rollback["required"] or not snapshot_ref):
        raise ContractError("ACT requires rollback.required and a snapshot_ref")

    context = _mapping(mission["context"], field="context")
    _reject_unknown(
        context,
        frozenset({"budget_tokens", "required_files", "optional_files"}),
        field="context",
    )
    if set(context) != {"budget_tokens", "required_files", "optional_files"}:
        raise ContractError(
            "context requires budget_tokens, required_files and optional_files"
        )
    normalized_context = {
        "budget_tokens": _positive_int(
            context["budget_tokens"], field="context.budget_tokens"
        ),
        "required_files": _paths(
            context["required_files"], field="context.required_files"
        ),
        "optional_files": _paths(
            context["optional_files"], field="context.optional_files"
        ),
    }

    normalized = {
        "schema": MISSION_SCHEMA,
        "mission_id": mission_id,
        "objective": objective,
        "scope": {"include": include, "exclude": exclude},
        "forbidden_actions": forbidden,
        "authority": authority,
        "risk": risk,
        "privacy": privacy,
        "capabilities": capabilities,
        "budgets": normalized_budgets,
        "required_evidence": evidence,
        "approval_gates": gates,
        "rollback": {
            "required": rollback["required"],
            "snapshot_ref": snapshot_ref,
        },
        "context": normalized_context,
    }
    if owner_ref:
        normalized["owner_approval_ref"] = owner_ref
    return normalized


def load_mission(path: str | Path) -> dict:
    """Read and validate a UTF-8 JSON mission file."""
    mission_path = Path(path)
    try:
        payload = json.loads(mission_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read mission {mission_path}: {exc}") from exc
    return validate_mission(payload)


def _file_entry(
    root: Path,
    relative: str,
    *,
    kind: str,
    required: bool,
    compressible: bool,
    reason: str,
) -> dict:
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"context file not found: {relative}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"context file escapes project root: {relative}") from exc
    if not resolved.is_file():
        raise ContractError(f"context entry is not a file: {relative}")
    data = resolved.read_bytes()
    return {
        "path": relative,
        "kind": kind,
        "sha256": hashlib.sha256(data).hexdigest(),
        "tokens_est": max(1, len(data) // 4),
        "required": required,
        "compressible": compressible,
        "reason": reason,
    }


def compile_context_manifest(
    project_root: str | Path,
    mission: Mapping,
    *,
    generated_at: str | None = None,
) -> dict:
    """Compile exact context metadata without storing file contents or host paths."""
    normalized = validate_mission(mission)
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ContractError(f"project root is not a directory: {project_root}")

    from skills.directives_audit import discover

    directive_paths = [
        item.path for item in discover(root) if item.kind == "instructions"
    ]
    pinned = []
    if (root / ".botte" / "policy.md").is_file():
        pinned.append(".botte/policy.md")
    pinned.extend(directive_paths)
    if not pinned:
        raise ContractError("no policy or agent directives can be pinned")

    required = normalized["context"]["required_files"]
    optional = normalized["context"]["optional_files"]
    budget = normalized["context"]["budget_tokens"]

    entries: list[dict] = []
    seen: set[str] = set()
    for relative in pinned:
        if relative in seen:
            continue
        kind = "policy" if relative == ".botte/policy.md" else "directive"
        entries.append(
            _file_entry(
                root,
                relative,
                kind=kind,
                required=True,
                compressible=False,
                reason="pinned safety/authority rule",
            )
        )
        seen.add(relative)

    for relative in required:
        if relative in seen:
            continue
        entries.append(
            _file_entry(
                root,
                relative,
                kind="mission-required",
                required=True,
                compressible=True,
                reason="mission required context",
            )
        )
        seen.add(relative)

    required_tokens = sum(item["tokens_est"] for item in entries)
    if required_tokens > budget:
        raise ContractError(
            f"pinned and required context costs {required_tokens} tokens, budget is {budget}"
        )

    omitted: list[dict] = []
    total = required_tokens
    for relative in optional:
        if relative in seen:
            continue
        try:
            candidate = _file_entry(
                root,
                relative,
                kind="mission-optional",
                required=False,
                compressible=True,
                reason="optional context within budget",
            )
        except ContractError as exc:
            omitted.append({"path": relative, "reason": str(exc)})
            continue
        if total + candidate["tokens_est"] > budget:
            omitted.append(
                {
                    "path": relative,
                    "reason": "context budget exceeded",
                    "tokens_est": candidate["tokens_est"],
                }
            )
            continue
        entries.append(candidate)
        seen.add(relative)
        total += candidate["tokens_est"]

    manifest = {
        "schema": CONTEXT_SCHEMA,
        "mission_id": normalized["mission_id"],
        "mission_sha256": contract_fingerprint(normalized),
        "generated_at": generated_at or _now(),
        "entries": entries,
        "omitted": omitted,
        "total_tokens_est": total,
        "budget_tokens": budget,
        "safety_rules_pinned": True,
        "raw_content_stored": False,
    }
    manifest["manifest_sha256"] = contract_fingerprint(manifest)
    return manifest


def _validate_lease(value, *, worker_id: str) -> dict:
    lease = _mapping(value, field="workspace_lease")
    allowed = frozenset(
        {
            "lease_id",
            "worker_id",
            "state",
            "base_sha",
            "head_sha",
            "expires_at",
            "workspace_fingerprint",
        }
    )
    _reject_unknown(lease, allowed, field="workspace_lease")
    if set(lease) != allowed:
        missing = sorted(allowed - set(lease))
        raise ContractError(f"workspace_lease is missing fields: {', '.join(missing)}")
    normalized = {
        "lease_id": _text(lease["lease_id"], field="workspace_lease.lease_id", maximum=128),
        "worker_id": _text(
            lease["worker_id"], field="workspace_lease.worker_id", maximum=128
        ),
        "state": _text(lease["state"], field="workspace_lease.state", maximum=16),
        "base_sha": _text(
            lease["base_sha"], field="workspace_lease.base_sha", maximum=64
        ),
        "head_sha": _text(
            lease["head_sha"], field="workspace_lease.head_sha", maximum=64, required=False
        ),
        "expires_at": _date_time(
            lease["expires_at"], field="workspace_lease.expires_at"
        ),
        "workspace_fingerprint": _text(
            lease["workspace_fingerprint"],
            field="workspace_lease.workspace_fingerprint",
            maximum=64,
        ),
    }
    if normalized["worker_id"] != worker_id:
        raise ContractError("workspace_lease.worker_id must match handoff worker_id")
    lease_id = normalized["lease_id"]
    if (
        not lease_id.startswith("wl_")
        or len(lease_id) != 19
        or any(ch not in "0123456789abcdef" for ch in lease_id[3:])
    ):
        raise ContractError("workspace_lease.lease_id has an invalid shape")
    if normalized["state"] not in LEASE_STATES:
        raise ContractError(f"workspace_lease.state must be one of {LEASE_STATES}")
    for name in ("base_sha", "head_sha"):
        value = normalized[name]
        if value and (
            len(value) not in (40, 64)
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise ContractError(f"workspace_lease.{name} must be a lowercase Git object ID")
    fingerprint = normalized["workspace_fingerprint"]
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise ContractError("workspace_lease.workspace_fingerprint must be a lowercase SHA-256")
    return normalized


def validate_handoff(payload: Mapping) -> dict:
    """Validate and normalize a ``botte.handoff/v1`` record."""
    handoff = _mapping(payload, field="handoff")
    _reject_unknown(handoff, _HANDOFF_FIELDS, field="handoff")
    missing = sorted(_HANDOFF_FIELDS - set(handoff))
    if missing:
        raise ContractError(f"handoff is missing fields: {', '.join(missing)}")
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise ContractError(f"schema must be {HANDOFF_SCHEMA}")

    mission_id = _text(handoff["mission_id"], field="mission_id", maximum=128)
    attempt_id = _text(handoff["attempt_id"], field="attempt_id", maximum=128)
    worker_id = _text(handoff["worker_id"], field="worker_id", maximum=128)
    created_at = _date_time(handoff["created_at"], field="created_at")
    status = _text(handoff["status"], field="status", maximum=32)
    if status not in HANDOFF_STATUSES:
        raise ContractError(f"status must be one of {HANDOFF_STATUSES}")
    lease = _validate_lease(handoff["workspace_lease"], worker_id=worker_id)

    checks_raw = handoff["checks"]
    if not isinstance(checks_raw, list) or len(checks_raw) > 100:
        raise ContractError("checks must be an array with at most 100 items")
    checks = []
    for index, raw in enumerate(checks_raw):
        check = _mapping(raw, field=f"checks[{index}]")
        _reject_unknown(check, frozenset({"name", "status", "evidence_ref"}), field="check")
        if set(check) != {"name", "status", "evidence_ref"}:
            raise ContractError("each check requires name, status and evidence_ref")
        check_status = _text(check["status"], field="check.status", maximum=16)
        if check_status not in CHECK_STATUSES:
            raise ContractError(f"check.status must be one of {CHECK_STATUSES}")
        checks.append(
            {
                "name": _text(check["name"], field="check.name", maximum=128),
                "status": check_status,
                "evidence_ref": _text(
                    check["evidence_ref"],
                    field="check.evidence_ref",
                    maximum=256,
                    required=False,
                ),
            }
        )

    evidence = _strings(
        handoff["evidence_refs"], field="evidence_refs", maximum=256, limit=100
    )
    artifacts_raw = handoff["artifacts"]
    if not isinstance(artifacts_raw, list) or len(artifacts_raw) > 100:
        raise ContractError("artifacts must be an array with at most 100 items")
    artifacts = []
    for index, raw in enumerate(artifacts_raw):
        artifact = _mapping(raw, field=f"artifacts[{index}]")
        _reject_unknown(artifact, frozenset({"kind", "ref", "sha256"}), field="artifact")
        if set(artifact) != {"kind", "ref", "sha256"}:
            raise ContractError("each artifact requires kind, ref and sha256")
        digest = _text(
            artifact["sha256"], field="artifact.sha256", maximum=64, required=False
        )
        if digest and (len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)):
            raise ContractError("artifact.sha256 must be a lowercase SHA-256")
        artifacts.append(
            {
                "kind": _text(artifact["kind"], field="artifact.kind", maximum=64),
                "ref": _text(artifact["ref"], field="artifact.ref", maximum=256),
                "sha256": digest,
            }
        )

    uncertainties = _strings(
        handoff["uncertainties"], field="uncertainties", maximum=512, limit=100
    )
    if not isinstance(handoff["approval_required"], bool):
        raise ContractError("approval_required must be a boolean")
    verdict = handoff["review_verdict"]
    if verdict is not None and verdict not in REVIEW_VERDICTS:
        raise ContractError(f"review_verdict must be null or one of {REVIEW_VERDICTS}")
    next_action = _text(
        handoff["next_safe_action"], field="next_safe_action", maximum=512
    )
    if handoff["safety_rules_pinned"] is not True:
        raise ContractError("safety_rules_pinned must be true")
    if handoff["raw_context_stored"] is not False:
        raise ContractError("raw_context_stored must be false")

    if status == "READY_FOR_REVIEW":
        if not evidence:
            raise ContractError("READY_FOR_REVIEW requires evidence_refs")
        if not checks or not any(item["status"] == "PASS" for item in checks):
            raise ContractError("READY_FOR_REVIEW requires at least one passing check")
        if any(item["status"] != "PASS" for item in checks):
            raise ContractError("READY_FOR_REVIEW requires every declared check to pass")
        if not lease["head_sha"]:
            raise ContractError("READY_FOR_REVIEW requires workspace_lease.head_sha")
    if verdict == "ACCEPT" and status != "READY_FOR_REVIEW":
        raise ContractError("ACCEPT is only valid for READY_FOR_REVIEW")

    normalized = {
        "schema": HANDOFF_SCHEMA,
        "mission_id": mission_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "created_at": created_at,
        "status": status,
        "workspace_lease": lease,
        "checks": checks,
        "evidence_refs": evidence,
        "artifacts": artifacts,
        "uncertainties": uncertainties,
        "approval_required": handoff["approval_required"],
        "review_verdict": verdict,
        "next_safe_action": next_action,
        "safety_rules_pinned": True,
        "raw_context_stored": False,
    }
    expected = contract_fingerprint(normalized)
    if handoff["handoff_sha256"] != expected:
        raise ContractError("handoff_sha256 does not match canonical handoff content")
    normalized["handoff_sha256"] = expected
    return normalized


def build_handoff(
    mission: Mapping,
    *,
    attempt_id: str,
    worker_id: str,
    status: str,
    workspace_lease: Mapping,
    checks: Iterable[Mapping] = (),
    evidence_refs: Iterable[str] = (),
    artifacts: Iterable[Mapping] = (),
    uncertainties: Iterable[str] = (),
    approval_required: bool = False,
    review_verdict: str | None = None,
    next_safe_action: str,
    created_at: str | None = None,
) -> dict:
    """Build and immediately validate a typed handoff record."""
    normalized_mission = validate_mission(mission)
    payload = {
        "schema": HANDOFF_SCHEMA,
        "mission_id": normalized_mission["mission_id"],
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "created_at": created_at or _now(),
        "status": status,
        "workspace_lease": dict(workspace_lease),
        "checks": [dict(item) for item in checks],
        "evidence_refs": list(evidence_refs),
        "artifacts": [dict(item) for item in artifacts],
        "uncertainties": list(uncertainties),
        "approval_required": approval_required,
        "review_verdict": review_verdict,
        "next_safe_action": next_safe_action,
        "safety_rules_pinned": True,
        "raw_context_stored": False,
    }
    payload["handoff_sha256"] = contract_fingerprint(payload)
    return validate_handoff(payload)


def resume_base_ref(mission: Mapping, handoff: Mapping) -> str:
    """Return the exact reviewed state from which a fresh session may resume."""
    normalized_mission = validate_mission(mission)
    normalized_handoff = validate_handoff(handoff)
    if normalized_mission["mission_id"] != normalized_handoff["mission_id"]:
        raise ContractError("resume handoff belongs to another mission")
    head_sha = normalized_handoff["workspace_lease"]["head_sha"]
    if not head_sha:
        raise ContractError("resume handoff has no bound head SHA")
    if normalized_handoff["workspace_lease"]["state"] == "QUARANTINED":
        raise ContractError("quarantined workspace evidence requires inspection before resume")
    return head_sha
