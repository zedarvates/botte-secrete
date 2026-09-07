"""Read-only effects declarations. Structural validity never grants authority."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SCHEMA = "botte.capability-effects/v1"
MAX_CONTRACT_BYTES = 64 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def _record(value: object, fields: set[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return False
    for key in sorted(fields - value.keys()):
        errors.append(f"{path}.{key}: required")
    for key in sorted(value.keys() - fields):
        errors.append(f"{path}.{key}: unknown field")
    return True


def _text(value: object, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected non-empty string")


def _strings(value: object, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return
    for i, item in enumerate(value):
        _text(item, f"{path}[{i}]", errors)


def _choice(value: object, choices: tuple[str, ...], path: str,
            errors: list[str]) -> None:
    if value not in choices:
        errors.append(f"{path}: expected one of {', '.join(choices)}")


def validate_contract(contract: object) -> list[str]:
    """Validate v1 declarations, without interpreting evidence or executing it."""
    errors: list[str] = []
    fields = {"schema", "capability_id", "contract_version", "source_hashes",
              "preconditions", "expected_effects", "downstream_effects",
              "reversibility", "retry", "required_scope", "analysis", "reuse"}
    if not _record(contract, fields, "$", errors):
        return errors
    if contract.get("schema") != SCHEMA:
        errors.append(f"$.schema: expected {SCHEMA}")
    for key in ("capability_id", "contract_version", "required_scope"):
        _text(contract.get(key), f"$.{key}", errors)
    _strings(contract.get("preconditions"), "$.preconditions", errors)
    hashes = contract.get("source_hashes")
    if not isinstance(hashes, dict) or "SKILL.md" not in hashes:
        errors.append("$.source_hashes: expected object including SKILL.md")
    if isinstance(hashes, dict):
        for name, digest in hashes.items():
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or ".." in path.parts
                    or "\\" in name or ":" in name or path.as_posix() != name):
                errors.append("$.source_hashes: paths must be relative to the skill")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                errors.append(f"$.source_hashes.{name}: expected SHA-256 hex digest")
    for key in ("expected_effects", "downstream_effects"):
        effects = contract.get(key)
        if not isinstance(effects, list):
            errors.append(f"$.{key}: expected array")
            continue
        if key == "expected_effects" and not effects:
            errors.append("$.expected_effects: describe at least one effect, even if unknown")
        for i, effect in enumerate(effects):
            path = f"$.{key}[{i}]"
            if not _record(effect, {"effect", "scope", "likelihood", "basis",
                                    "impact", "verification"}, path, errors):
                continue
            for field in ("effect", "scope", "basis", "impact", "verification"):
                _text(effect.get(field), f"{path}.{field}", errors)
            _choice(effect.get("likelihood"),
                    ("conditional", "probable", "plausible", "unknown"),
                    f"{path}.likelihood", errors)
    reversal = contract.get("reversibility")
    if _record(reversal, {"status", "strategy", "residual_effects"},
               "$.reversibility", errors):
        _choice(reversal.get("status"),
                ("read_only", "reversible", "partial", "irreversible", "unknown"),
                "$.reversibility.status", errors)
        _text(reversal.get("strategy"), "$.reversibility.strategy", errors)
        _strings(reversal.get("residual_effects"), "$.reversibility.residual_effects", errors)
    retry = contract.get("retry")
    if _record(retry, {"semantics", "check_before_retry", "stop_condition"}, "$.retry", errors):
        _choice(retry.get("semantics"),
                ("idempotent", "conditional", "non_idempotent", "unknown"),
                "$.retry.semantics", errors)
        for field in ("check_before_retry", "stop_condition"):
            _text(retry.get(field), f"$.retry.{field}", errors)
    analysis = contract.get("analysis")
    if _record(analysis, {"summary", "uncertainties", "evidence_refs"}, "$.analysis", errors):
        _text(analysis.get("summary"), "$.analysis.summary", errors)
        for field in ("uncertainties", "evidence_refs"):
            _strings(analysis.get(field), f"$.analysis.{field}", errors)
    reuse = contract.get("reuse")
    if not isinstance(reuse, list):
        errors.append("$.reuse: expected array")
    else:
        for i, item in enumerate(reuse):
            path = f"$.reuse[{i}]"
            if not _record(item, {"target", "rationale", "adaptations", "validation",
                                  "status", "validated_context", "evidence_refs"}, path, errors):
                continue
            for field in ("target", "rationale", "validation"):
                _text(item.get(field), f"{path}.{field}", errors)
            for field in ("adaptations", "evidence_refs"):
                _strings(item.get(field), f"{path}.{field}", errors)
            _choice(item.get("status"),
                    ("validated_in_context", "adaptation_to_test", "exploratory"),
                    f"{path}.status", errors)
            if item.get("validated_context") is not None:
                _text(item.get("validated_context"), f"{path}.validated_context", errors)
            if item.get("status") == "validated_in_context":
                _text(item.get("validated_context"), f"{path}.validated_context", errors)
                if not item.get("evidence_refs"):
                    errors.append(f"{path}.evidence_refs: validated reuse needs evidence")
    return errors


def _read_bounded(path: Path, limit: int) -> bytes:
    if not path.is_file():
        raise ValueError("expected regular file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("file exceeds size limit")
    return raw


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def inspect_effects(skill_dir: Path, *, expected_id: str | None = None) -> dict:
    """Load effects.json and check only its explicitly bound local sources.

    Missing, invalid and stale declarations are distinct from 'declared'. The
    latter means identity and bound sources match, never behavior verified.
    External trees need an expected_id supplied by the caller, not the sidecar.
    """
    root = Path(skill_dir).resolve()
    sidecar = root / "effects.json"
    if not sidecar.exists() and not sidecar.is_symlink():
        return {"status": "missing", "errors": []}
    try:
        if not sidecar.resolve().is_relative_to(root):
            raise ValueError("effects.json must stay within the skill directory")
        contract = json.loads(_read_bounded(sidecar, MAX_CONTRACT_BYTES).decode("utf-8"),
                              object_pairs_hook=_unique_object)
        errors = validate_contract(contract)
    except (OSError, ValueError, RecursionError, RuntimeError):
        return {"status": "invalid", "errors": ["effects.json: unreadable, oversized or invalid JSON"]}
    if errors:
        return {"status": "invalid", "errors": errors}
    if expected_id is None:
        from skills.capabilities.registry import REPO_ROOT
        if root.is_relative_to(REPO_ROOT / "skills"):
            expected_id = "zedarvates/botte-secrete:" + root.relative_to(REPO_ROOT).as_posix()
    if not isinstance(expected_id, str) or not expected_id.strip():
        return {"status": "invalid", "errors": [
            "capability_id: supply expected_id for a skill outside the bundled tree"]}
    if contract["capability_id"] != expected_id:
        return {"status": "invalid", "errors": [
            "capability_id: does not match the identity resolved by the caller"]}
    stale = []
    for name, expected in contract["source_hashes"].items():
        try:
            source = (root / name).resolve()
            if not source.is_relative_to(root):
                raise ValueError("source outside skill directory")
            actual = hashlib.sha256(_read_bounded(source, MAX_SOURCE_BYTES)).hexdigest()
            if actual != expected:
                stale.append(f"{name}: source hash changed")
        except (OSError, ValueError, RuntimeError):
            stale.append(f"{name}: source unavailable or outside skill directory")
    return {"status": "stale" if stale else "declared", "errors": stale,
            "contract": contract}


def contract_template(skill_dir: Path, capability_id: str) -> dict:
    """Draft only: no inferred safety, authority, measured probability or reuse."""
    digest = hashlib.sha256(_read_bounded(Path(skill_dir) / "SKILL.md", MAX_SOURCE_BYTES)).hexdigest()
    return {
        "schema": SCHEMA, "capability_id": capability_id, "contract_version": "0.1.0-draft",
        "source_hashes": {"SKILL.md": digest},
        "preconditions": ["Not assessed; identify inputs, environment and dependencies."],
        "expected_effects": [{
            "effect": "Not assessed; describe the intended change or output.",
            "scope": "Not assessed; identify affected resources and recipients.",
            "likelihood": "unknown", "basis": "No reviewed execution evidence.",
            "impact": "Not assessed; describe benefits, losses, resource use and data exposure.",
            "verification": "Define an observable check proportional to this effect."
        }],
        "downstream_effects": [],
        "reversibility": {"status": "unknown", "strategy": "Not assessed.",
                          "residual_effects": ["Not assessed."]},
        "retry": {"semantics": "unknown",
                  "check_before_retry": "Inspect actual state; a timeout does not prove non-execution.",
                  "stop_condition": "Do not retry an uncertain mutation before resolving its state."},
        "required_scope": "Not assessed; use the current task's existing authorization.",
        "analysis": {"summary": "Draft declaration; complete it from implementation and evidence.",
                     "uncertainties": ["Direct and downstream effects are not assessed.",
                                       "Only SKILL.md is bound; add implementation source hashes."],
                     "evidence_refs": []},
        "reuse": [{"target": "Not assessed; identify a possible next use.",
                   "rationale": "Explain which mechanism or result could transfer and why.",
                   "adaptations": ["Identify changed inputs, environment, scope and costs."],
                   "validation": "Define the smallest check in the target context.",
                   "status": "exploratory", "validated_context": None, "evidence_refs": []}]
    }
