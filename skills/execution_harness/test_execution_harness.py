#!/usr/bin/env python3
"""Focused invariant tests for the execution harness contracts."""

from __future__ import annotations

import tempfile
from copy import deepcopy
import json
from pathlib import Path

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
from skills.execution_harness.atlas_seed import (
    NEEDLE2_COMPARISON_REF, NEEDLE2_COMPARISON_SHA256, _validate_summary,
    atlas_from_needle2_comparison,
)
from skills.execution_harness.memory_adapter import build_checkpoint_proposal
from skills.execution_harness.trajectory_adapter import emit_harness_outcome


def _raises(fn, exception=HarnessInvariantError) -> bool:
    try:
        fn()
    except exception:
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

    requested = {"quality": {"level": "full"}}
    executed = deepcopy(requested)
    alias_harness = ExecutionHarness(mission="alias-check", context_snapshot={})
    alias_harness.record_delta(ExecutionDelta(requested=requested, executed=executed))
    executed["quality"]["level"] = "reduced"
    recorded = alias_harness.build_handoff(completed=(), remaining=())["execution_deltas"][0]
    check(
        "caller mutation cannot rewrite recorded nested execution states",
        recorded["requested"] == recorded["executed"] == {"quality": {"level": "full"}}
        and executed["quality"]["level"] == "reduced",
    )
    alias_harness.execution_deltas[0].executed["quality"]["level"] = "reduced"
    check(
        "handoff rejects an internally edited unacknowledged degradation",
        _raises(lambda: alias_harness.build_handoff(completed=(), remaining=())),
    )

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

    source_bytes = Path(NEEDLE2_COMPARISON_REF).read_bytes()
    with tempfile.TemporaryDirectory() as seed_dir:
        alternate = Path(seed_dir) / "comparison.json"
        alternate.write_bytes(source_bytes)
        copied = atlas_from_needle2_comparison(alternate)
        check(
            "seed binds copied historical bytes rather than trusting their filename",
            len(copied.observations) == 2
            and all(f"file-sha256:{NEEDLE2_COMPARISON_SHA256}" in row.evidence_refs
                    for row in copied.observations),
        )
        alternate.write_bytes(source_bytes + b"\n")
        check(
            "even whitespace drift cannot become source-bound historical observations",
            _raises(lambda: atlas_from_needle2_comparison(alternate), ValueError),
        )
        fabricated = json.loads(source_bytes)
        fabricated["protocol_sha256"] = "not-a-hash"
        fabricated["needle_diagnostic"]["positive_exact_coverage"] = 42
        alternate.write_text(json.dumps(fabricated), encoding="utf-8")
        check(
            "fabricated protocol and metrics cannot acquire historical model provenance",
            _raises(lambda: atlas_from_needle2_comparison(alternate), ValueError),
        )

    valid_summary = json.loads(source_bytes)["needle_diagnostic"]
    for field, value in (
        ("p95_roundtrip_ms", float("nan")),
        ("p95_roundtrip_ms", -1),
        ("positive_exact_coverage", 42),
        ("positive_cases", 0),
        ("positive_exact_calls", True),
        ("proposals", 1),
        ("exact_proposal_precision", 1),
    ):
        invalid_summary = {**valid_summary, field: value}
        check(
            f"Atlas seed rejects invalid measurement or denominator {field}={value!r}",
            _raises(lambda: _validate_summary(invalid_summary), ValueError),
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

    checkpoint_harness = ExecutionHarness(mission="current-checkpoint", context_snapshot={})
    checkpoint_harness.build_handoff(completed=("first",), remaining=("reconcile",))
    checkpoint_harness.uncertainties.append("unresolved action")
    checkpoint_harness.record_delta(ExecutionDelta(
        requested={"model": "requested"}, executed={"model": "fallback"},
        reason="backend unavailable", acknowledged=True,
    ))
    fresh_proposal = build_checkpoint_proposal(
        checkpoint_harness, project_id="test-project", key="harness.current.v1",
        request_id="req-current-1", run_id="run-current-1", observed_at=1_800_000_000.0,
    )
    checkpoint = json.loads(fresh_proposal["arguments"]["record"]["text"])
    check(
        "checkpoint rebuilds current uncertainty and deltas while retaining progress",
        checkpoint["uncertainties"] == ["unresolved action"]
        and len(checkpoint["execution_deltas"]) == 1
        and checkpoint["completed"] == ["first"]
        and checkpoint["remaining"] == ["reconcile"],
    )

    for declaration in (
        "CC-BY-NC-4.0",
        "CC BY-NC 4.0",
        "CC_BY_NC_4.0",
        "CC BY NC 4.0",
        "NonCommercial",
        "non-commercial",
        "non commercial",
        " \tNoN_Commercial\n",
    ):
        check(
            f"commercial use rejects non-commercial declaration {declaration!r}",
            _raises(
                lambda: harness.validate_commercial_weights_policy(
                    commercial_use=True,
                    weights_license=declaration,
                )
            ),
        )

    for declaration in (
        "",
        " \t\n",
        "unknown",
        " UNKNOWN ",
        "unspecified",
        "unqualified",
        "tbd",
        "n/a",
        "none",
        "NOASSERTION",
    ):
        check(
            f"commercial use rejects missing/unknown declaration {declaration!r}",
            _raises(
                lambda: harness.validate_commercial_weights_policy(
                    commercial_use=True,
                    weights_license=declaration,
                )
            ),
        )

    # These are declarations, not verified licences or commercial approvals.
    # Custom terms still need source-backed qualification outside this helper.
    for declaration in ("Apache-2.0", "MIT", "LicenseRef-custom"):
        check(
            f"declaration check returns no approval value for {declaration!r}",
            harness.validate_commercial_weights_policy(
                commercial_use=True,
                weights_license=declaration,
            ) is None,
        )

    for declaration in ("CC-BY-NC-4.0", "unknown", ""):
        check(
            f"commercial-only guard adds no decision for non-commercial use: {declaration!r}",
            harness.validate_commercial_weights_policy(
                commercial_use=False,
                weights_license=declaration,
            ) is None,
        )

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
