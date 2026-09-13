#!/usr/bin/env python3
"""Focused invariant tests for the execution harness contracts."""

from __future__ import annotations

from skills.execution_harness import (
    ArtifactRecord,
    CapabilityAtlas,
    CapabilityObservation,
    EvidenceRecord,
    ExecutionDelta,
    ExecutionHarness,
    ExplorationCandidate,
    HarnessInvariantError,
    VerificationResult,
)
from skills.execution_harness.atlas_seed import atlas_from_needle2_comparison


def _raises(fn) -> bool:
    try:
        fn()
    except HarnessInvariantError:
        return True
    return False


def main() -> int:
    passed = failed = 0

    def check(label: str, condition: bool) -> None:
        nonlocal passed, failed
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if condition:
            passed += 1
        else:
            failed += 1

    print("== execution harness tests ==")
    harness = ExecutionHarness(mission="test", context_snapshot={"sha": "abc"})

    check(
        "silent degradation is rejected",
        _raises(
            lambda: harness.record_delta(
                ExecutionDelta(
                    requested={"quality": "full"},
                    executed={"quality": "reduced"},
                )
            )
        ),
    )
    harness.record_delta(
        ExecutionDelta(
            requested={"quality": "full"},
            executed={"quality": "reduced"},
            reason="VRAM limit observed",
            acknowledged=True,
        )
    )
    check("explicit execution delta is retained", len(harness.execution_deltas) == 1)

    verified = ArtifactRecord(
        artifact_id="build-1",
        digest="sha256:good",
        status="verified",
        evidence_refs=("ci:1",),
    )
    harness.set_last_known_good(verified)
    harness.retain_failed_candidate(
        ArtifactRecord(
            artifact_id="build-2",
            digest="sha256:bad",
            status="failed",
            evidence_refs=("ci:2",),
        )
    )
    check(
        "failed candidate cannot replace last-known-good",
        harness.recovery_point is not None
        and harness.recovery_point.artifact_id == "build-1",
    )

    candidate = ExplorationCandidate(
        candidate_id="idea-a",
        producer_id="agent-a",
        claim="candidate finding",
    )
    check(
        "cross-pollination without evidence is rejected",
        _raises(candidate.cross_pollination_packet),
    )
    gated = ExplorationCandidate(
        candidate_id="idea-b",
        producer_id="agent-a",
        claim="candidate finding",
        evidence_refs=("test:fixture",),
        evidence_gate_passed=True,
    )
    check("evidence-gated finding can be shared", gated.cross_pollination_packet()["candidate_id"] == "idea-b")
    check(
        "producer cannot independently verify itself",
        _raises(
            lambda: gated.validate_independent_verification(
                VerificationResult(
                    verifier_id="agent-a",
                    passed=True,
                    evidence_refs=("test:fixture",),
                )
            )
        ),
    )

    atlas = CapabilityAtlas()
    atlas.record(
        CapabilityObservation(
            task="tool-selection",
            model="tiny-model",
            harness="baseline",
            hardware="cpu",
            quality_score=0.4,
            evidence_refs=("bench:baseline",),
        )
    )
    atlas.record(
        CapabilityObservation(
            task="tool-selection",
            model="tiny-model",
            harness="evidence-harness",
            hardware="cpu",
            quality_score=0.7,
            evidence_refs=("bench:harness",),
        )
    )
    rows = atlas.comparable(task="tool-selection", hardware="cpu")
    check(
        "model x harness observations remain distinct",
        len(rows) == 2 and rows[0].comparison_key != rows[1].comparison_key,
    )
    check(
        "atlas refuses unevidenced observations",
        _raises(
            lambda: atlas.record(
                CapabilityObservation(
                    task="tool-selection",
                    model="tiny-model",
                    harness="unknown",
                    hardware="cpu",
                )
            )
        ),
    )

    seeded = atlas_from_needle2_comparison()
    seed_rows = seeded.comparable(task="memory-tool-selection-fr-calibration-v1", hardware="cpu-study-host")
    check(
        "existing real Needle/Qwen comparison seeds source-bound Atlas observations",
        len(seed_rows) == 2
        and {row.model for row in seed_rows} == {"Needle 2", "Qwen2.5-0.5B Instruct"}
        and all(row.evidence_refs for row in seed_rows),
    )
    check(
        "seed preserves harness distinction and non-promotion outcomes",
        seed_rows[0].comparison_key != seed_rows[1].comparison_key
        and all("promotion" in row.outcome or "stop_" in row.outcome for row in seed_rows),
    )

    harness.add_evidence(EvidenceRecord(kind="ci", ref="ci:1", verified=True))
    handoff = harness.build_handoff(completed=("contract",), remaining=("integration",))
    check("handoff carries recovery and execution deltas", bool(handoff["recovery_point"]) and len(handoff["execution_deltas"]) == 1)

    check(
        "non-commercial weights are blocked for commercial promotion",
        _raises(
            lambda: harness.validate_commercial_weights_policy(
                commercial_use=True,
                weights_license="CC-BY-NC-4.0",
            )
        ),
    )

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
