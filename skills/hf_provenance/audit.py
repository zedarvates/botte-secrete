"""Compare an authoritative model directory with an exported Hub snapshot.

The audit is deliberately offline.  A caller must first download the public Hub
files into a bounded directory, then pass that directory here.  This keeps CI
hermetic and prevents a publication check from silently trusting live network
state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROVENANCE_KEYS = {
    "data",
    "dataset",
    "eval",
    "eval_accuracy",
    "held_out_accuracy",
    "provenance",
    "samples",
    "trained_at",
    "trained_on",
}


def _model_entry(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    entry: dict[str, Any] = {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "json_valid": False,
        "provenance_keys": [],
    }
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return entry
    if not isinstance(data, dict):
        return entry
    entry["json_valid"] = True
    entry["provenance_keys"] = sorted(PROVENANCE_KEYS.intersection(data))
    return entry


def _inventory(directory: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"model directory does not exist: {root}")
    return {path.name: _model_entry(path) for path in sorted(root.glob("*.json"))}


def audit_snapshot(
    source_dir: str | Path,
    snapshot_dir: str | Path,
    *,
    hub_repo: str | None = None,
    hub_revision: str | None = None,
    source_revision: str | None = None,
    grounding_verdicts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, JSON-serialisable publication gate report."""
    source = _inventory(source_dir)
    snapshot = _inventory(snapshot_dir)
    if grounding_verdicts is not None:
        for name, entry in source.items():
            verdict = grounding_verdicts.get(Path(name).stem, "missing audit verdict")
            entry["grounding_verdict"] = verdict
            entry["grounded"] = verdict == "grounded"
    shared = sorted(source.keys() & snapshot.keys())
    missing = sorted(source.keys() - snapshot.keys())
    hub_only = sorted(snapshot.keys() - source.keys())
    matches = [name for name in shared if source[name]["sha256"] == snapshot[name]["sha256"]]
    mismatches = [name for name in shared if name not in matches]
    invalid_source = sorted(name for name, item in source.items() if not item["json_valid"])
    missing_provenance = sorted(
        name for name, item in source.items() if not item["provenance_keys"]
    )
    not_grounded = sorted(
        name for name, item in source.items() if grounding_verdicts is not None
        and not item.get("grounded", False)
    )

    reasons: list[str] = []
    if not source:
        reasons.append("authoritative source inventory is empty")
    if missing:
        reasons.append("Hub snapshot does not contain the complete source inventory")
    if hub_only:
        reasons.append("Hub snapshot contains files absent from the authoritative source")
    if mismatches:
        reasons.append("shared Hub files do not match authoritative SHA-256 digests")
    if invalid_source:
        reasons.append("authoritative source contains invalid model JSON")
    if missing_provenance:
        reasons.append("authoritative source models are missing provenance metadata")
    if not_grounded:
        reasons.append("authoritative source models are not grounded by nn_audit")

    return {
        "schema_version": 1,
        "hub_repo": hub_repo,
        "hub_revision": hub_revision,
        "source_revision": source_revision,
        "source_models": [source[name] for name in sorted(source)],
        "hub_models": [snapshot[name] for name in sorted(snapshot)],
        "comparison": {
            "source_model_count": len(source),
            "hub_model_count": len(snapshot),
            "shared": shared,
            "exact_matches": matches,
            "hash_mismatches": mismatches,
            "missing_on_hub": missing,
            "hub_only": hub_only,
            "invalid_source_json": invalid_source,
            "source_missing_provenance": missing_provenance,
            "source_not_grounded": not_grounded,
        },
        "publish_weights_allowed": not reasons,
        "block_reasons": reasons,
    }
