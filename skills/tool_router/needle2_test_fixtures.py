"""Test-only software fixtures, separate from the frozen model study.

Nothing here overwrites a historical protocol, corpus, report or source binding.
The temporary protocol describes the current verifier and authored fake cases;
it is not a new inference study or evidence of model quality.
"""
from __future__ import annotations

import json

import pytest

from . import needle2_study as study


IMMUTABLE_JSON = (
    "needle2-study-protocol-v1.json",
    "needle2-study-calibration-native-v1.json",
    "needle2-study-calibration-generalist-v1.json",
    "needle2-study-selection-v1.json",
    "needle2-study-comparison-v1.json",
)
MANIFEST_SHA256 = "ae0e81102fff746ab72039a1a5b2f5ee02b6e3e372be73f7e79f639ee3a706c0"


def historical_bindings():
    """Inspect recorded bindings; do not accept them as current qualification."""
    manifest_path = study.ROOT / "docs/validation/needle2-study-validation-v1.json"
    raw = manifest_path.read_bytes()
    assert study.digest(raw) == MANIFEST_SHA256, "historical manifest changed"
    manifest = study.read_json(manifest_path)
    protocol = study.read_json(study.PROTOCOL)
    drift = {
        name: expected
        for name, expected in protocol["source_sha256"].items()
        if study.digest((study.ROOT / name).read_bytes()) != expected
    }
    attachment_drift = {
        name: expected
        for name, expected in manifest["evidence_sha256"].items()
        if study.digest((study.ROOT / name).read_bytes()) != expected
    }
    return manifest, protocol, drift, attachment_drift


@pytest.fixture
def integration_protocol(tmp_path, monkeypatch):
    """Create two 20-case synthetic contract fixtures under a temporary root."""
    actual_root = study.ROOT
    root = tmp_path / "integration-source"
    root.mkdir()
    frozen = study.read_json(study.PROTOCOL)
    source_sha256 = {}
    for name in frozen["source_sha256"]:
        data = (actual_root / name).read_bytes()
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        source_sha256[name] = study.digest(data)
    specs = list(study.memory_tools())
    protocol = {
        "schema_version": "botte.needle2-study-protocol/v1",
        "qualification_scope": "temporary_software_fixture_not_inference_evidence",
        "source_sha256": source_sha256,
        "catalog_sha256": study.catalog_sha256(),
        "needle_library_sha256": "0" * 64,
        "thresholds": [0, .65, .9],
        "splits": {},
    }
    for split in ("calibration", "validation"):
        cases = []
        for number in range(10):
            tool = specs[number % len(specs)].name
            arguments = ({"key": f"fixture-key-{number}"} if tool == "memory_history" else
                         {"text": f"fixture text {number}"} if tool == "memory_scribe" else {})
            cases.append({
                "id": f"fixture-{split}-positive-{number}", "kind": "software_fixture",
                "query": f"Synthetic contract {split} positive {number}",
                "expected_tool": tool, "expected_arguments": arguments,
            })
            cases.append({
                "id": f"fixture-{split}-negative-{number}", "kind": "software_fixture",
                "query": f"Synthetic contract {split} negative {number}",
                "expected_tool": None, "expected_arguments": {},
            })
        relative = f"fixtures/{split}.jsonl"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = ("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)).encode("utf-8")
        target.write_bytes(raw)
        protocol["splits"][split] = {"path": relative, "sha256": study.digest(raw)}
    target = root / "integration-protocol.json"
    study.write_json(target, protocol)
    monkeypatch.setattr(study, "ROOT", root)
    yield target
