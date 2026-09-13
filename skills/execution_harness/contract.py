"""Small, dependency-free contracts for auditable agent execution.

The module is intentionally policy-first.  It does not execute tools or models;
it records what was requested, what actually ran, the evidence produced, and
which candidate may become the last-known-good artifact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


class HarnessInvariantError(ValueError):
    """Raised when an execution would lose an auditable safety invariant."""


@dataclass(frozen=True)
class EvidenceRecord:
    kind: str
    ref: str
    verified: bool = False
    note: str = ""


@dataclass(frozen=True)
class Consequence:
    resource: str
    effect: str
    reversible: bool
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionDelta:
    requested: dict[str, Any]
    executed: dict[str, Any]
    reason: str = ""
    acknowledged: bool = False

    @property
    def changed(self) -> bool:
        return self.requested != self.executed

    def validate(self) -> None:
        if self.changed and (not self.acknowledged or not self.reason.strip()):
            raise HarnessInvariantError(
                "requested_state differs from executed_state; record an explicit "
                "reason and acknowledgement instead of degrading silently"
            )


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    digest: str
    status: str = "candidate"
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryPoint:
    artifact_id: str
    digest: str
    note: str = "last-known-good"


@dataclass(frozen=True)
class VerificationResult:
    verifier_id: str
    passed: bool
    evidence_refs: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class ExplorationCandidate:
    candidate_id: str
    producer_id: str
    claim: str
    evidence_refs: tuple[str, ...] = ()
    evidence_gate_passed: bool = False

    def cross_pollination_packet(self) -> dict[str, Any]:
        if not self.evidence_gate_passed or not self.evidence_refs:
            raise HarnessInvariantError(
                "cross-pollination requires evidence and a passed evidence gate"
            )
        return {
            "candidate_id": self.candidate_id,
            "producer_id": self.producer_id,
            "claim": self.claim,
            "evidence_refs": list(self.evidence_refs),
        }

    def validate_independent_verification(self, result: VerificationResult) -> None:
        if result.verifier_id == self.producer_id:
            raise HarnessInvariantError(
                "independent verification must use a verifier distinct from the producer"
            )
        if result.passed and not result.evidence_refs:
            raise HarnessInvariantError("a passing verification must reference evidence")


@dataclass(frozen=True)
class CapabilityObservation:
    task: str
    model: str
    harness: str
    hardware: str
    quantization: str = ""
    latency_ms: float | None = None
    quality_score: float | None = None
    outcome: str = "observed"
    failure_mode: str = ""
    evidence_refs: tuple[str, ...] = ()

    @property
    def comparison_key(self) -> tuple[str, str, str, str, str]:
        # Harness is deliberately part of the identity: model-only comparisons
        # must not collapse observations made under materially different harnesses.
        return (
            self.task,
            self.model,
            self.harness,
            self.hardware,
            self.quantization,
        )


@dataclass
class CapabilityAtlas:
    observations: list[CapabilityObservation] = field(default_factory=list)

    def record(self, observation: CapabilityObservation) -> None:
        if not observation.evidence_refs:
            raise HarnessInvariantError(
                "Capability Atlas observations require at least one evidence reference"
            )
        self.observations.append(observation)

    def comparable(
        self,
        *,
        task: str,
        hardware: str | None = None,
    ) -> list[CapabilityObservation]:
        return [
            item
            for item in self.observations
            if item.task == task and (hardware is None or item.hardware == hardware)
        ]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.observations]


@dataclass
class ExecutionHarness:
    mission: str
    context_snapshot: dict[str, Any]
    capabilities: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    plan: tuple[str, ...] = ()
    evidence: list[EvidenceRecord] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    consequences: list[Consequence] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    execution_deltas: list[ExecutionDelta] = field(default_factory=list)
    recovery_point: RecoveryPoint | None = None
    handoff: dict[str, Any] = field(default_factory=dict)

    def record_delta(self, delta: ExecutionDelta) -> None:
        delta.validate()
        self.execution_deltas.append(delta)

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        self.evidence.append(evidence)

    def add_consequence(self, consequence: Consequence) -> None:
        self.consequences.append(consequence)

    def set_last_known_good(self, artifact: ArtifactRecord) -> None:
        if artifact.status != "verified":
            raise HarnessInvariantError(
                "only a verified artifact may become the last-known-good recovery point"
            )
        if not artifact.evidence_refs:
            raise HarnessInvariantError(
                "last-known-good promotion requires verification evidence"
            )
        self.recovery_point = RecoveryPoint(
            artifact_id=artifact.artifact_id,
            digest=artifact.digest,
        )
        self.artifacts.append(artifact)

    def retain_failed_candidate(self, artifact: ArtifactRecord) -> None:
        if artifact.status != "failed":
            raise HarnessInvariantError("failed-candidate retention expects status='failed'")
        # Deliberately do not mutate recovery_point.
        self.artifacts.append(artifact)

    def build_handoff(self, *, completed: Iterable[str], remaining: Iterable[str]) -> dict[str, Any]:
        unverified = [item.ref for item in self.evidence if not item.verified]
        self.handoff = {
            "mission": self.mission,
            "completed": list(completed),
            "remaining": list(remaining),
            "recovery_point": asdict(self.recovery_point) if self.recovery_point else None,
            "uncertainties": list(self.uncertainties),
            "unverified_evidence": unverified,
            "consequences": [asdict(item) for item in self.consequences],
            "execution_deltas": [asdict(item) for item in self.execution_deltas],
        }
        return self.handoff

    def validate_commercial_weights_policy(
        self,
        *,
        commercial_use: bool,
        weights_license: str,
    ) -> None:
        """Reject declared non-commercial terms and missing/unknown declarations.

        This checks a caller-supplied string, not the actual weight licence.
        Returning None never establishes rights: custom terms and other licence
        declarations still require source-backed qualification before use.
        """
        if not commercial_use:
            return

        normalized = re.sub(r"[\s_-]+", "", weights_license.casefold())
        if normalized in {
            "", "unknown", "unspecified", "unqualified", "tbd", "n/a", "none",
            "noassertion",
        }:
            raise HarnessInvariantError(
                "commercial use requires a known weights licence declaration"
            )
        if "noncommercial" in normalized or "bync" in normalized:
            raise HarnessInvariantError(
                "non-commercial model weights cannot be promoted into a commercial workflow"
            )
