"""Executor — run a local-model call through the harness's five layers.

    gate → constrain → ground → verify → (abstain|escalate) → learn

The point: a small local model handles what it can, structurally constrained and
deterministically checked; anything it can't ground is escalated, never returned as
fiction. Dependencies (effort, client, escalation) are injectable so the whole flow
is testable without a live backend. See docs/plans/2026-06-26_local-model-harness-spec.md.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from skills.local_harness.spec import HarnessSpec
from skills.local_harness import verifier


@dataclass
class HarnessResult:
    answer: Any
    source: str                      # local | escalated | abstained | gated
    escalated: bool = False
    reason: str = ""
    verifications: dict = field(default_factory=dict)
    samples: int = 0

    def to_dict(self) -> dict:
        return {"answer": self.answer, "source": self.source,
                "escalated": self.escalated, "reason": self.reason,
                "verifications": self.verifications, "samples": self.samples}


# ── default dependency wiring (lazy so the module imports without a backend) ──

def _default_effort(task: str, task_type: str) -> float:
    from skills.auto_router.effort import estimate
    return estimate(task, task_type=task_type).score


def _default_client():
    from skills.llm_backends.client import LocalLLMClient
    return LocalLLMClient()


def _default_escalate(task: str, tier: str) -> str:
    from skills.auto_router import fusion
    return (fusion.cascade(task).get("answer") or "")


def _build_prompt(spec: HarnessSpec, task: str, context: Optional[str]) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for KV-cache-friendly local inference.

    The system prompt is STABLE across calls — same instruction every time,
    enabling Ollama/LM Studio prefix caching (no re-computation of KV-cache
    for the shared prefix). The user prompt carries the variable context + task.
    """
    system = (
        "You are a precise, honest assistant. Answer the task using ONLY the "
        "context provided. If the answer is not in the context, reply exactly "
        f"'{spec.escalate_token}'. Never guess or fabricate."
    )
    if spec.ground_source != "none" and context:
        user = f"## Context\n{context}\n\n## Task\n{task}"
    else:
        user = task
    return system, user


def _consensus(outputs: list[dict], agree: int) -> Optional[dict]:
    """Return the output that appears >= `agree` times (by JSON identity), else None."""
    if not outputs:
        return None
    counts: dict[str, int] = {}
    rep: dict[str, dict] = {}
    for o in outputs:
        key = json.dumps(o, sort_keys=True, default=str)
        counts[key] = counts.get(key, 0) + 1
        rep[key] = o
    best = max(counts, key=counts.get)
    return rep[best] if counts[best] >= agree else None


def _wants_escalation(out: Any, token: str) -> bool:
    return token and token.lower() in json.dumps(out, default=str).lower()


def run_harness(spec: HarnessSpec, task: str, *, task_type: str = "",
                context: Optional[str] = None, repo_root: str = ".",
                client=None, effort_fn: Optional[Callable] = None,
                escalate_fn: Optional[Callable] = None,
                outcome_project_root: str | Path | None = None,
                outcome_execution_id: str = "",
                outcome_risk: str = "standard",
                permission_profile: str = "") -> HarnessResult:
    started = time.perf_counter()
    effort_fn = effort_fn or _default_effort
    escalate_fn = escalate_fn or _default_escalate

    def _finish(result: HarnessResult, *, status: str, verdict: str | None = None,
                verified_by: str = "", evidence_refs=(), acted: bool = False,
                approval_required: bool = False) -> HarnessResult:
        """Emit private QA facts without letting observability break execution."""
        try:
            from skills.trajectory.outcome import emit_outcome
            emit_outcome(
                task,
                project_root=outcome_project_root or repo_root,
                execution_id=outcome_execution_id,
                source="local_harness",
                task_type=task_type,
                route="local",
                status=status,
                verdict=verdict,
                verified_by=verified_by,
                evidence_refs=evidence_refs,
                risk=outcome_risk,
                permission_profile=permission_profile,
                model=spec.model,
                harness=spec.name,
                tool_versions={"local_harness": "v1"},
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                acted=acted,
                abstained=result.source == "abstained",
                escalated=result.escalated,
                approval_required=approval_required,
            )
        except Exception:  # noqa: BLE001 — outcome logging is best-effort
            pass
        return result

    def _escalate(reason: str, source: str = "escalated", verifications=None) -> HarnessResult:
        if spec.on_fail == "abstain" and source != "gated":
            return HarnessResult(answer=None, source="abstained", reason=reason,
                                 verifications=verifications or {})
        ans = escalate_fn(task, spec.escalate_to)
        return HarnessResult(answer=ans, source=source, escalated=True, reason=reason,
                             verifications=verifications or {})

    # 1 · GATE — don't even ask the local model what it reliably gets wrong.
    score = effort_fn(task, task_type)
    if score > spec.max_effort:
        return _finish(
            _escalate(f"gate: effort {score:.2f} > {spec.max_effort}", source="gated"),
            status="ESCALATED",
        )
    if spec.allow_task_types and task_type and task_type not in spec.allow_task_types:
        return _finish(
            _escalate(f"gate: task_type '{task_type}' not allowed", source="gated"),
            status="ESCALATED",
        )
    # Strict mode: silently refuse critical/security tasks instead of risking hallucination
    if spec.strict and task_type in ("critical_fix", "security_audit", "architecture"):
        return _finish(
            _escalate(f"gate: strict mode — '{task_type}' must use cloud", source="gated"),
            status="APPROVAL_REQUIRED", approval_required=True,
        )

    # 2·3 · GROUND + CONSTRAIN — structured output, optionally grounded.
    sys_prompt, user_prompt = _build_prompt(spec, task, context)
    client = client or _default_client()
    outputs: list[dict] = []
    for _ in range(max(1, spec.samples)):
        try:
            outputs.append(client.chat_json(user_prompt, schema=spec.output_schema,
                                             system=sys_prompt, max_tokens=spec.max_tokens))
        except Exception as e:  # noqa: BLE001 — local failure ⇒ escalate, don't crash
            result = _escalate(f"local call failed: {e}")
            return _finish(
                result,
                status="ABSTAINED" if result.source == "abstained" else "ESCALATED",
                verdict="FAIL",
                verified_by=f"harness:{spec.name}",
                evidence_refs=(f"harness:{spec.name}:local_call:failed",),
                acted=True,
            )

    out = _consensus(outputs, spec.agree)
    if out is None:
        result = _escalate(f"no self-consistency consensus over {len(outputs)} samples")
        return _finish(
            result,
            status="ABSTAINED" if result.source == "abstained" else "ESCALATED",
            verdict="UNCERTAIN",
            verified_by=f"harness:{spec.name}",
            evidence_refs=(f"harness:{spec.name}:consensus:failed",),
            acted=True,
        )
    if _wants_escalation(out, spec.escalate_token):
        result = _escalate("model returned the escalate token (not in context)")
        return _finish(
            result,
            status="ABSTAINED" if result.source == "abstained" else "ESCALATED",
            verdict="UNCERTAIN",
            verified_by=f"harness:{spec.name}",
            evidence_refs=(f"harness:{spec.name}:escalate_token",),
            acted=True,
        )

    # 4 · VERIFY — deterministic checks; a claim it can't ground fails here.
    vres = verifier.verify(out, spec.verify, context=context, repo_root=repo_root,
                           schema=spec.output_schema)
    checks = vres.to_dict()["checks"]

    # 5 · DECIDE
    if vres.ok:
        result = HarnessResult(answer=out, source="local", verifications=checks,
                               samples=len(outputs))
        final_status = "PASS"
        final_verdict = "PASS"
        evidence_refs = tuple(
            f"harness:{spec.name}:{name}:pass" for name in sorted(checks)
        )
    else:
        failed = [n for n, c in checks.items() if not c["ok"]]
        result = _escalate(f"verification failed: {failed}", verifications=checks)
        final_status = "ABSTAINED" if result.source == "abstained" else "ESCALATED"
        final_verdict = "FAIL"
        evidence_refs = tuple(
            f"harness:{spec.name}:{name}:fail" for name in sorted(failed)
        )

    # 6 · LEARN — feed the outcome back (best-effort).
    if spec.learn:
        try:
            from skills.botte_nn.active_learning import record_feedback
            record_feedback("binary_router", [score, 1.0, 1.0],
                            predicted_class=0, actual_class=(0 if result.source == "local" else 1))
        except Exception:  # noqa: BLE001
            pass
    return _finish(
        result,
        status=final_status,
        verdict=final_verdict,
        verified_by=f"harness:{spec.name}" if evidence_refs else "",
        evidence_refs=evidence_refs,
        acted=True,
    )
