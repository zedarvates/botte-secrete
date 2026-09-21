"""Source-bound Capability Atlas adapters for existing verified study artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from .contract import CapabilityAtlas, CapabilityObservation

NEEDLE2_COMPARISON_REF = "docs/validation/needle2-study-comparison-v1.json"


def atlas_from_needle2_comparison(path: str | Path = NEEDLE2_COMPARISON_REF) -> CapabilityAtlas:
    """Convert the existing Needle/Qwen study into non-activating Atlas observations.

    The source report compares different runtime paths and explicitly disallows a
    speedup claim, so latency is retained as an observation but never normalized
    into a performance winner here.
    """
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "botte.needle2-study-comparison/v1":
        raise ValueError("unsupported Needle study comparison schema")
    if payload.get("activation_allowed") is not False or payload.get("executed") is not False:
        raise ValueError("seed adapter expects the consultative, non-executing study boundary")

    protocol = payload.get("protocol_sha256", "")
    evidence = (f"file:{source.as_posix()}", f"protocol-sha256:{protocol}")
    limitations = ",".join(payload.get("limitations", []))

    atlas = CapabilityAtlas()
    needle = payload["needle_diagnostic"]
    atlas.record(CapabilityObservation(
        task="memory-tool-selection-fr-calibration-v1",
        model="Needle 2",
        harness="needle-native-consultative-v1",
        hardware="cpu-study-host",
        quantization="native",
        latency_ms=float(needle["p95_roundtrip_ms"]),
        quality_score=float(needle["positive_exact_coverage"]),
        outcome="stop_insufficient_safe_coverage",
        failure_mode=f"precision={needle['exact_proposal_precision']};limitations={limitations}",
        evidence_refs=evidence,
    ))

    generalist = payload["generalist"]
    atlas.record(CapabilityObservation(
        task="memory-tool-selection-fr-calibration-v1",
        model="Qwen2.5-0.5B Instruct",
        harness="openai-compatible-json-selection-v1",
        hardware="cpu-study-host",
        quantization="Q8_0",
        latency_ms=float(generalist["p95_roundtrip_ms"]),
        quality_score=float(generalist["positive_exact_coverage"]),
        outcome="comparison_only_no_promotion",
        failure_mode=f"precision={generalist['exact_proposal_precision']};limitations={limitations}",
        evidence_refs=evidence,
    ))
    return atlas
