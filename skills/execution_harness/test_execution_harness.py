#!/usr/bin/env python3
"""Focused invariant tests for the execution harness contracts."""

from __future__ import annotations

import tempfile

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
from skills.execution_harness.memory_adapter import build_checkpoint_proposal
from skills.execution_harness.trajectory_adapter import emit_harness_outcome


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
    harness.add_evidence(EvidenceRecord(kind="note", ref="unverified:note", verified=False))
    handoff = harness.build_handoff(completed=("contract",), remaining=("integration",))
    check("handoff carries recovery and execution deltas", bool(handoff["recovery_point"]) and len(handoff["execution_deltas"]) == 1)

    with tempfile.TemporaryDirectory() as project:
        emitted = emit_harness_outcome(
            harness,
            task="verify harness bridge",
            route="local",
            status="UNCERTAIN",
            project_root=project,
            execution_id="execution-harness-test-1",
            task_type="harness-contract",
            tags=("shadow", "test"),
            model="none",
        )
        envelope = emitted["envelope"]
        check(
            "trajectory bridge remains shadow-only and non-activating",
            envelope["shadow_only"] is True
            and envelope["activation_allowed"] is False
            and envelope["acted"] is False,
        )
        check(
            "trajectory bridge passes verified harness evidence without self-promoting it",
            envelope["evidence_refs"] == ["ci:1"]
            and envelope["verification_state"] == "rejected"
            and envelope["verified"] is False,
        )

    proposal = build_checkpoint_proposal(
        harness,
        project_id="test-project",
        key="harness.checkpoint.v1",
        request_id="req-harness-1",
        run_id="run-harness-1",
        observed_at=1_800_000_000.0,
    )
    check(
        "memory adapter produces a validated non-executing checkpoint proposal",
        proposal["operation"] == "checkpoint"
        and proposal["executed"] is False
        and proposal["memory_write_performed"] is False
        and proposal["activation_allowed"] is False
        and proposal["review_required"] is True,
    )
    check(
        "memory proposal carries only verified evidence and no injected authority",
        proposal["arguments"]["record"]["evidence_refs"] == ["ci:1"]
        and "agent_id" not in proposal["arguments"]
        and "trust_class" not in proposal["arguments"]
        and "status" not in proposal["arguments"],
    )

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
