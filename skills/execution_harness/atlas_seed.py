"""Source-bound Capability Atlas adapters for existing verified study artifacts."""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import stat

from .contract import CapabilityAtlas, CapabilityObservation

NEEDLE2_COMPARISON_REF = "docs/validation/needle2-study-comparison-v1.json"
NEEDLE2_COMPARISON_SHA256 = "87d4071b34b476725e390f8ded65ff4af300e4107757933df3ae7073accb3868"
NEEDLE2_PROTOCOL_SHA256 = "212eaeeb5aa2dc7874e1e887e4ae608cc8c55bf8dc65a1d9120165335a1ee026"
MAX_COMPARISON_BYTES = 65_536


def _read_comparison(source: Path) -> bytes:
    if source.is_symlink():
        raise ValueError("comparison source must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("comparison source must be a regular file")
        raw = handle.read(MAX_COMPARISON_BYTES + 1)
    if len(raw) > MAX_COMPARISON_BYTES:
        raise ValueError("comparison source exceeds its byte limit")
    return raw


def _validate_summary(summary: object) -> None:
    if not isinstance(summary, dict):
        raise ValueError("comparison summary must be an object")
    counts = (
        "positive_cases", "negative_cases", "proposals", "positive_exact_calls",
        "positive_wrong_proposals", "negative_proposals", "runtime_errors",
    )
    if any(type(summary.get(key)) is not int or summary[key] < 0 for key in counts):
        raise ValueError("comparison counts must be non-negative integers")
    positive = summary["positive_cases"]
    exact = summary["positive_exact_calls"]
    wrong = summary["positive_wrong_proposals"]
    negative_proposals = summary["negative_proposals"]
    proposals = summary["proposals"]
    if (positive <= 0 or exact + wrong > positive
            or negative_proposals > summary["negative_cases"]
            or proposals != exact + wrong + negative_proposals
            or summary["runtime_errors"] != 0):
        raise ValueError("comparison counts have inconsistent denominators or runtime failures")
    for key, maximum in (("p95_roundtrip_ms", None), ("positive_exact_coverage", 1.0)):
        value = summary.get(key)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or value < 0 or (maximum is not None and value > maximum)):
            raise ValueError("comparison measurement must be finite and within bounds: " + key)
    precision = summary.get("exact_proposal_precision")
    if proposals == 0:
        if precision is not None:
            raise ValueError("comparison precision must remain unknown without proposals")
    elif (type(precision) not in (int, float) or not math.isfinite(precision)
          or not 0 <= precision <= 1 or precision != exact / proposals):
        raise ValueError("comparison precision differs from its denominator")
    if summary["positive_exact_coverage"] != exact / positive:
        raise ValueError("comparison coverage differs from its denominator")


def atlas_from_needle2_comparison(path: str | Path = NEEDLE2_COMPARISON_REF) -> CapabilityAtlas:
    """Convert the existing Needle/Qwen study into non-activating Atlas observations.

    The source report compares different runtime paths and explicitly disallows a
    speedup claim, so latency is retained as an observation but never normalized
    into a performance winner here.
    """
    source = Path(path)
    raw = _read_comparison(source)
    if hashlib.sha256(raw).hexdigest() != NEEDLE2_COMPARISON_SHA256:
        raise ValueError("comparison differs from the pinned historical archive")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema_version") != "botte.needle2-study-comparison/v1":
        raise ValueError("unsupported Needle study comparison schema")
    if payload.get("activation_allowed") is not False or payload.get("executed") is not False:
        raise ValueError("seed adapter expects the consultative, non-executing study boundary")

    protocol = payload.get("protocol_sha256", "")
    if protocol != NEEDLE2_PROTOCOL_SHA256 or payload.get("split") != "calibration":
        raise ValueError("comparison protocol or split differs from the pinned study")
    if payload.get("speedup_claim_allowed") is not False:
        raise ValueError("historical comparison cannot establish a speedup claim")
    evidence = (f"file:{source.as_posix()}", f"file-sha256:{NEEDLE2_COMPARISON_SHA256}",
                f"protocol-sha256:{protocol}")
    limitations = ",".join(payload.get("limitations", []))

    atlas = CapabilityAtlas()
    needle = payload["needle_diagnostic"]
    _validate_summary(needle)
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
    _validate_summary(generalist)
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
