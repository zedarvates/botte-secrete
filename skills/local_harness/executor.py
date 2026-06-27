"""Executor — run a local-model call through the harness's five layers.

    gate → constrain → ground → verify → (abstain|escalate) → learn

The point: a small local model handles what it can, structurally constrained and
deterministically checked; anything it can't ground is escalated, never returned as
fiction. Dependencies (effort, client, escalation) are injectable so the whole flow
is testable without a live backend. See docs/plans/2026-06-26_local-model-harness-spec.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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


def _build_prompt(spec: HarnessSpec, task: str, context: Optional[str]) -> str:
    if spec.ground_source != "none" and context:
        return (
            f"Answer the task using ONLY the context below. If the answer is not in "
            f"the context, reply exactly '{spec.escalate_token}'.\n\n"
            f"## Context\n{context}\n\n## Task\n{task}"
        )
    return task


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
                escalate_fn: Optional[Callable] = None) -> HarnessResult:
    effort_fn = effort_fn or _default_effort
    escalate_fn = escalate_fn or _default_escalate

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
        return _escalate(f"gate: effort {score:.2f} > {spec.max_effort}", source="gated")
    if spec.allow_task_types and task_type and task_type not in spec.allow_task_types:
        return _escalate(f"gate: task_type '{task_type}' not allowed", source="gated")

    # 2·3 · GROUND + CONSTRAIN — structured output, optionally grounded.
    prompt = _build_prompt(spec, task, context)
    client = client or _default_client()
    outputs: list[dict] = []
    for _ in range(max(1, spec.samples)):
        try:
            outputs.append(client.chat_json(prompt, schema=spec.output_schema,
                                             max_tokens=spec.max_tokens))
        except Exception as e:  # noqa: BLE001 — local failure ⇒ escalate, don't crash
            return _escalate(f"local call failed: {e}")

    out = _consensus(outputs, spec.agree)
    if out is None:
        return _escalate(f"no self-consistency consensus over {len(outputs)} samples")
    if _wants_escalation(out, spec.escalate_token):
        return _escalate("model returned the escalate token (not in context)")

    # 4 · VERIFY — deterministic checks; a claim it can't ground fails here.
    vres = verifier.verify(out, spec.verify, context=context, repo_root=repo_root,
                           schema=spec.output_schema)
    checks = vres.to_dict()["checks"]

    # 5 · DECIDE
    if vres.ok:
        result = HarnessResult(answer=out, source="local", verifications=checks,
                               samples=len(outputs))
    else:
        failed = [n for n, c in checks.items() if not c["ok"]]
        result = _escalate(f"verification failed: {failed}", verifications=checks)

    # 6 · LEARN — feed the outcome back (best-effort).
    if spec.learn:
        try:
            from skills.botte_nn.active_learning import record_feedback
            record_feedback("binary_router", [score, 1.0, 1.0],
                            predicted_class=0, actual_class=(0 if result.source == "local" else 1))
        except Exception:  # noqa: BLE001
            pass
    return result
