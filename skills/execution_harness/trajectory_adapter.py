"""Advisory bridge from ExecutionHarness state to trajectory outcome envelopes.

This adapter deliberately does not execute anything, alter routing, or persist
CapabilityAtlas observations.  It only converts already-observed harness state
into the existing shadow-only trajectory envelope contract.
"""

from __future__ import annotations

from typing import Iterable

from skills.execution_harness.contract import ExecutionHarness
from skills.trajectory.outcome import emit_outcome


def emit_harness_outcome(
    harness: ExecutionHarness,
    *,
    task: str,
    route: str,
    status: str,
    project_root: str = ".",
    execution_id: str = "",
    source: str = "execution-harness",
    task_type: str = "",
    tags: Iterable[str] = (),
    verdict: str | None = None,
    verified_by: str = "",
    evidence_refs: Iterable[str] | None = None,
    quality_score: float | None = None,
    risk: str = "standard",
    model: str = "",
    harness_name: str = "execution-harness-v1",
) -> dict:
    """Emit one shadow-only trajectory envelope from a completed harness view.

    Evidence is explicit.  When omitted, only verified harness evidence is used.
    This function never turns consequences, deltas, or recovery points into
    activation authority.
    """
    refs = list(evidence_refs) if evidence_refs is not None else [
        item.ref for item in harness.evidence if item.verified
    ]
    result = emit_outcome(
        task,
        route=route,
        status=status,
        project_root=project_root,
        execution_id=execution_id,
        source=source,
        task_type=task_type,
        tags=tags,
        verdict=verdict,
        verified_by=verified_by,
        evidence_refs=refs,
        quality_score=quality_score,
        risk=risk,
        model=model,
        harness=harness_name,
        acted=False,
    )
    envelope = result["envelope"]
    if envelope.get("activation_allowed") is not False or envelope.get("shadow_only") is not True:
        raise RuntimeError("trajectory adapter must remain shadow-only and non-activating")
    return result


__all__ = ["emit_harness_outcome"]
