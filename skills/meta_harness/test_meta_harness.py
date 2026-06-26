#!/usr/bin/env python3
"""Tests for meta_harness — orchestrator, runner, governance, session, CLI.

    python -m skills.meta_harness.test_meta_harness
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.meta_harness import MetaHarness, PipelinePlan, Step
from skills.meta_harness import Sandbox, Governance, ApprovalGate, Session
from skills.meta_harness.governance import Governance
from skills.meta_harness.session import Session


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== meta_harness tests ==")

    # ── MetaHarness basics ──
    h = MetaHarness(workdir=".")
    _ok("MetaHarness initializes", isinstance(h, MetaHarness), state)

    # ── List agents ──
    agents = h.list_agents()
    _ok("list_agents returns list", isinstance(agents, list), state)
    _ok("list_agents has at least 3 agents", len(agents) >= 3, state)
    agent_names = [a["name"] for a in agents]
    _ok("porthos is in agent list", "porthos" in agent_names, state)
    _ok("security is in agent list", "security" in agent_names, state)

    # ── List plans ──
    plans = h.list_plans()
    _ok("list_plans returns dict", isinstance(plans, dict), state)
    _ok("audit plan exists", "audit" in plans, state)
    _ok("full plan exists", "full" in plans, state)

    # ── Plan creation ──
    plan = h.plan(["security", "fast_context"])
    _ok("plan creates steps", len(plan.steps) > 0, state)
    _ok("plan steps are Step instances",
        all(isinstance(s, Step) for s in plan.steps), state)
    _ok("first step agent matches", plan.steps[0].agent != "", state)

    # ── Built-in plan ──
    audit_plan = h.plan(h.list_plans()["audit"])
    _ok("built-in audit plan has steps", len(audit_plan.steps) > 0, state)

    # ── Plan metadata ──
    _ok("plan has name", len(plan.name) > 0, state)
    _ok("plan.created_at > 0", plan.created_at > 0, state)
    _ok("new plan is not complete", not plan.is_complete, state)
    _ok("new plan has not failed", not plan.has_failed, state)

    # ── Execution with simple command ──
    simple_plan = h.plan(["test"])
    # This won't actually run pytest successfully without a proper project
    # But it tests the execution flow
    session = h.execute(simple_plan)
    _ok("session has results", len(session.results) > 0, state)
    _ok("session report is non-empty", len(session.report()) > 0, state)

    # ── Governance ──
    g = Governance(require_approval=False)
    gate = g.check(Step(agent="test", command=["echo", "hello"]))
    _ok("simple command passes governance", gate.approved, state)
    _ok("simple command is not blocked", not gate.blocked, state)

    g2 = Governance(require_approval=True)
    gate2 = g2.check(Step(agent="fix", command=["rm", "-rf", "/"]))
    _ok("destructive command is blocked", gate2.blocked, state)

    g3 = Governance(require_approval=True)
    gate3 = g3.check(Step(agent="audit", command=["python3", "audit.py"]))
    _ok("approval-required blocks non-destructive", gate3.blocked, state)
    _ok("approval-required asks for human", gate3.requires_human, state)

    # ── Approval gate ──
    gate_ok = ApprovalGate(approved=True)
    _ok("ApprovalGate approved", gate_ok.approved and not gate_ok.blocked, state)

    gate_blocked = ApprovalGate(approved=False, blocked=True, reason="test")
    _ok("ApprovalGate blocked", gate_blocked.blocked, state)
    _ok("ApprovalGate reason", gate_blocked.reason == "test", state)

    # ── Session ──
    s = Session(name="test_session")
    _ok("Session creates storage dir",
        Path(".botte-cache/sessions/").exists(), state)
    _ok("Session has started_at", s.started_at > 0, state)

    # ── Step status ──
    step1 = Step(agent="audit", command=["echo", "audit complete"])
    step1.status = "passed"
    s.add_result(step1)

    step2 = Step(agent="fix", command=["echo", "fix complete"])
    step2.status = "failed"
    step2.exit_code = 1
    step2.output = "Error: something broke"
    s.add_result(step2)

    _ok("session has 2 results", len(s.results) == 2, state)
    _ok("session report mentions failed step", "failed" in s.report(), state)
    _ok("session report shows agent names", "audit" in s.report(), state)
    _ok("session to_json() is valid JSON", '"results"' in s.to_json(), state)

    # ── Sandbox ──
    sandbox = Sandbox(workdir=".", sandbox_dir=".botte-sandbox/test")
    result = sandbox.run(["echo", "hello world"])
    _ok("sandbox runs echo successfully", result.success, state)
    _ok("sandbox captures stdout", "hello world" in result.stdout, state)
    _ok("sandbox exit_code is 0", result.exit_code == 0, state)
    _ok("sandbox duration > 0", result.duration > 0, state)

    # ── Sandbox: failed command ──
    fail = sandbox.run(["false"])
    _ok("sandbox false command fails", not fail.success, state)

    # ── Sandbox: nonexistent command ──
    no_cmd = sandbox.run(["this_command_does_not_exist_xyz"])
    _ok("sandbox nonexistent command fails", not no_cmd.success, state)
    _ok("sandbox reports file not found", "not found" in no_cmd.stderr, state)

    # ── Sandbox cleanup ──
    sandbox2 = Sandbox(workdir=".", sandbox_dir=".botte-sandbox/cleanup_test")
    sandbox2.run(["echo", "create"])
    _ok("sandbox dir exists", Path(sandbox2.sandbox_dir).exists(), state)
    sandbox2.cleanup()
    _ok("sandbox cleanup removes dir", not Path(sandbox2.sandbox_dir).exists(), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
