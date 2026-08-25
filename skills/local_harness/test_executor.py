#!/usr/bin/env python3
"""Tests for local_harness.executor — the five-layer harness, stubbed end to end.

    python -m skills.local_harness.test_executor
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.local_harness.spec import HarnessSpec
from skills.local_harness.executor import run_harness
from skills.trajectory.outcome import load_outcomes
from skills.trajectory.quality import load_verified


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


class StubClient:
    """Canned chat_json (or raises) — no backend needed."""
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, 0

    def chat_json(self, prompt, *, schema=None, system=None, max_tokens=512, **kw):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.reply


SCHEMA = {"type": "object", "required": ["answer", "evidence"],
          "properties": {"answer": {"type": "string"},
                         "evidence": {"type": "array"}}}


def _spec(**kw):
    base = dict(max_effort=0.45, output_schema=SCHEMA,
                verify=["schema", "evidence_in_context"],
                ground_source="files:.", on_fail="escalate")
    base.update(kw)
    return HarnessSpec(**base)


def main() -> int:
    state = [0, 0]
    print("== local_harness.executor tests ==")

    ctx = "The retry budget is 3 attempts and the timeout is 30 seconds."
    low_effort = lambda task, tt: 0.2
    escalate = lambda task, tier: "CLOUD_ANSWER"
    project_tmp = tempfile.TemporaryDirectory()
    project = project_tmp.name

    # 1. Happy path: grounded, schema-valid → trusted locally.
    c = StubClient({"answer": "3 attempts", "evidence": ["retry budget is 3"]})
    r = run_harness(_spec(), "how many retries?", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="happy")
    _ok("grounded + valid → source=local", r.source == "local" and not r.escalated, state)
    _ok("grounded checks emit a verified PASS envelope",
        load_outcomes(project)[-1]["status"] == "PASS"
        and load_outcomes(project)[-1]["verified"]
        and load_verified(project)[-1]["verdict"] == "PASS", state)

    # 2. Hallucination: evidence not in context → verify fails → escalate.
    c = StubClient({"answer": "5 minutes", "evidence": ["timeout is 5 minutes"]})
    r = run_harness(_spec(), "what timeout?", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="hallucination")
    _ok("ungrounded evidence → escalated (not returned as fact)",
        r.source == "escalated" and r.escalated and r.answer == "CLOUD_ANSWER", state)
    _ok("escalation records which check failed",
        r.verifications.get("evidence_in_context", {}).get("ok") is False, state)
    _ok("failed deterministic verification emits a verified local FAIL",
        load_outcomes(project)[-1]["status"] == "ESCALATED"
        and load_outcomes(project)[-1]["verdict"] == "FAIL"
        and load_verified(project)[-1]["verdict"] == "FAIL", state)

    # 3. Gate: too hard → escalate without ever calling the local model.
    c = StubClient({"answer": "x", "evidence": []})
    r = run_harness(_spec(), "prove P=NP", context=ctx, client=c,
                    effort_fn=lambda t, tt: 0.9, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="effort-gate")
    _ok("high effort → source=gated, model not called", r.source == "gated" and c.calls == 0, state)

    # 4. Abstain policy: verify fails + on_fail=abstain → no answer, no cloud.
    c = StubClient({"answer": "made up", "evidence": ["not in the context at all"]})
    r = run_harness(_spec(on_fail="abstain"), "q", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="abstain")
    _ok("on_fail=abstain → source=abstained, answer=None",
        r.source == "abstained" and r.answer is None, state)
    _ok("abstention is explicit in the outcome envelope",
        load_outcomes(project)[-1]["status"] == "ABSTAINED"
        and load_outcomes(project)[-1]["abstained"], state)

    # 5. Model self-reports it doesn't know → escalate.
    c = StubClient({"answer": "NEEDS_ESCALATION", "evidence": []})
    r = run_harness(_spec(), "q", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="escalate-token")
    _ok("escalate token → escalated", r.source == "escalated", state)

    # 6. Local call failure → escalate, never crash.
    c = StubClient(exc=RuntimeError("backend down"))
    r = run_harness(_spec(), "q", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="backend-failure")
    _ok("local failure → escalated (no crash)",
        r.source == "escalated" and "failed" in r.reason, state)

    # 7. Strict critical work produces an approval-required envelope without a call.
    c = StubClient({"answer": "x", "evidence": []})
    r = run_harness(_spec(strict=True, max_effort=1.0), "audit credentials",
                    task_type="security_audit", context=ctx, client=c,
                    effort_fn=low_effort, escalate_fn=escalate,
                    repo_root=project, outcome_execution_id="approval-gate",
                    outcome_risk="high")
    _ok("strict critical gate requires approval and never calls the local model",
        r.source == "gated" and c.calls == 0
        and load_outcomes(project)[-1]["status"] == "APPROVAL_REQUIRED"
        and load_outcomes(project)[-1]["approval_required"], state)

    # 8. Spec loads from the shipped YAML example.
    spec = HarnessSpec.load(_REPO / "examples" / "harnesses" / "local-extract.yaml")
    _ok("HarnessSpec.load parses the YAML example",
        spec.name == "local-extract-v1" and spec.max_effort == 0.45
        and "evidence_in_context" in spec.verify and spec.output_format == "json_schema",
        state)

    project_tmp.cleanup()

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
