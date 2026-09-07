"""Adversarial checks for proof scope, blocking decisions and durable budgets."""

from __future__ import annotations

import json
import importlib.util
import io
import tempfile
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from skills.meta_harness.review import CheckpointRegistry, ReviewError, review_handoff
from skills.meta_harness.lease import WorktreeLeaseManager
from skills.meta_harness import MetaHarness, PipelinePlan, Step
from skills.meta_harness.review_cli import main as review_cli
from skills.meta_harness.test_reliable_run import _init_repo, _mission, _review_lease, _run
from skills.run_contract import build_handoff
from skills.safe_exit import SafeExitConfig


def check(ref="tests:project", status="PASS"):
    return {"name": "independent-replay", "status": status, "evidence_ref": ref}


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.mission = _mission()
        self.author = _review_lease("phaseone", "c" * 64)
        self.reviewer = _review_lease("phasetwo", "d" * 64)

    def review(self, *, mission=None, checks=None, approval=False, evidence=None,
               reviewer=None, previous=(), closed=()):
        mission = mission or self.mission
        handoff = build_handoff(
            mission, attempt_id="attempt-1", worker_id="phaseone",
            status="READY_FOR_REVIEW", workspace_lease=self.author,
            checks=[check()], evidence_refs=evidence or ["tests:project"],
            approval_required=approval, next_safe_action="Independent review.",
        )
        return review_handoff(
            mission, handoff, reviewer_id="phasetwo",
            review_workspace_lease=reviewer or self.reviewer,
            replayed_checks=checks if checks is not None else [check()],
            previous_failure_refs=previous, closed_failure_refs=closed,
        )

    def test_replayed_required_proof_can_be_accepted(self):
        self.assertEqual(self.review()["verdict"], "ACCEPT")

    def test_unrelated_pass_cannot_validate_authors_claim(self):
        result = self.review(checks=[check("docs:spelling")])
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("missing_required_replay:tests:project", result["reasons"])

    def test_partial_replay_does_not_cover_the_other_required_proof(self):
        result = self.review(
            mission=_mission(required_evidence=["tests:project", "audit:security"]),
            evidence=["tests:project", "audit:security"],
        )
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_review_exports_only_observed_refs(self):
        result = self.review(evidence=["tests:project", "author:unobserved"])
        self.assertEqual(result["evidence_refs"], ["tests:project"])

    def test_required_failure_is_rework(self):
        self.assertEqual(self.review(checks=[check(status="FAIL")])["verdict"], "REWORK")

    def test_human_block_wins_over_failure(self):
        result = self.review(approval=True, checks=[check(status="FAIL")])
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(result["approval_required"])

    def test_owner_only_risk_cannot_be_downgraded_by_a_failure(self):
        result = self.review(mission=_mission(risk="R4", approval_gates=["owner-review"]),
                             checks=[check(status="FAIL")])
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(result["approval_required"])

    def test_missing_proof_wins_over_unrelated_failure(self):
        result = self.review(checks=[check("docs:spelling", "FAIL")])
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_incomplete_replay_wins_over_failure(self):
        result = self.review(checks=[check(status="FAIL"), check("other:proof", "SKIPPED")])
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_unclosed_failure_cannot_override_approval(self):
        result = self.review(approval=True, previous=["tests:project"])
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_failure_closure_needs_its_own_passing_replay(self):
        result = self.review(previous=["audit:security"], closed=["audit:security"])
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_observed_prior_failure_can_be_closed(self):
        result = self.review(previous=["tests:project"], closed=["tests:project"])
        self.assertEqual(result["verdict"], "ACCEPT")

    def test_closure_of_an_unreported_failure_is_blocked(self):
        self.assertEqual(self.review(closed=["tests:project"])["verdict"], "BLOCKED")

    def test_reviewer_must_use_the_same_base_and_head_as_author_head(self):
        for field in ("base_sha", "head_sha"):
            with self.subTest(field=field), self.assertRaises(ReviewError):
                self.review(reviewer={**self.reviewer, field: "e" * 40})

    def test_reused_lease_id_does_not_become_independent_by_renaming_worker(self):
        with self.assertRaises(ReviewError):
            self.review(reviewer={**self.reviewer, "lease_id": self.author["lease_id"]})

    def test_expired_or_unzoned_review_lease_is_rejected(self):
        for expiry in ("2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00"):
            with self.subTest(expiry=expiry), self.assertRaises(ReviewError):
                self.review(reviewer={**self.reviewer, "expires_at": expiry})


class RevisionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = CheckpointRegistry(self.tmp.name)
        self.mission = _mission()
        self.registry.register_attempt(self.mission, attempt_id="initial")

    def test_renamed_failures_cannot_reset_total_budget(self):
        for i in range(2):
            self.registry.register_attempt(self.mission, attempt_id=f"retry-{i}",
                                           addressed_failure_refs=[f"failure:{i}"])
        with self.assertRaises(ReviewError):
            self.registry.register_attempt(self.mission, attempt_id="retry-new",
                                           addressed_failure_refs=["failure:new"])

    def test_fresh_instance_retains_budget_and_idempotent_attempt(self):
        for i in range(2):
            self.registry.register_attempt(self.mission, attempt_id=f"retry-{i}",
                                           addressed_failure_refs=["failure:one"])
        fresh = CheckpointRegistry(self.tmp.name)
        state = fresh.register_attempt(self.mission, attempt_id="retry-1",
                                        addressed_failure_refs=["failure:one"])
        self.assertEqual(len(state["attempts"]), 3)
        with self.assertRaises(ReviewError):
            fresh.register_attempt(self.mission, attempt_id="retry-2",
                                    addressed_failure_refs=["failure:one"])

    def test_mission_budget_cannot_be_silently_increased(self):
        changed = _mission(budgets={**self.mission["budgets"], "max_revisions": 100})
        with self.assertRaises(ReviewError):
            self.registry.register_attempt(changed, attempt_id="retry-1",
                                           addressed_failure_refs=["failure:one"])

    def test_required_proof_cannot_be_removed_from_a_running_mission(self):
        changed = _mission(required_evidence=["docs:spelling"])
        with self.assertRaises(ReviewError):
            self.registry.register_attempt(changed, attempt_id="retry-1",
                                           addressed_failure_refs=["failure:one"])

    def test_legacy_attempts_are_preserved_and_need_reconciliation(self):
        path = self.registry._path(self.mission["mission_id"])
        state = json.loads(path.read_text(encoding="utf-8"))
        state.pop("mission_sha256")
        text = json.dumps(state)
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ReviewError):
            self.registry.register_attempt(self.mission, attempt_id="retry-1",
                                           addressed_failure_refs=["failure:one"])
        self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_permission_error_does_not_create_a_new_budget(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with self.assertRaises(ReviewError):
                self.registry.load(self.mission["mission_id"])

    def test_competing_attempts_share_one_persistent_budget(self):
        def attempt(i):
            try:
                CheckpointRegistry(self.tmp.name).register_attempt(
                    self.mission, attempt_id=f"retry-{i}", addressed_failure_refs=[f"failure:{i}"])
                return True
            except ReviewError:
                return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            accepted = list(pool.map(attempt, range(6)))
        self.assertEqual(sum(accepted), 2)
        self.assertEqual(len(self.registry.load(self.mission["mission_id"])["attempts"]), 3)


class RunnerBudgetTests(unittest.TestCase):
    def test_last_allowed_call_does_not_allow_one_more(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = MetaHarness(directory, safe_exit_config=SafeExitConfig(max_tool_calls=1))
            plan = PipelinePlan(name="bounded", steps=[
                Step(agent=f"test-{i}", command=[sys.executable, "-c", "print('ok')"])
                for i in range(3)
            ])
            session = harness.execute(plan)
        self.assertEqual([r.status for r in session.results], ["passed", "skipped", "skipped"])
        self.assertEqual(session.termination_reason, "tool_budget_exhausted")

    def test_child_timeout_uses_remaining_wall_time(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = MetaHarness(directory, safe_exit_config=SafeExitConfig(max_wall_seconds=0.05))
            plan = PipelinePlan(name="bounded-time", steps=[
                Step(agent="slow", command=[sys.executable, "-c", "import time; time.sleep(3)"]),
                Step(agent="next", command=[sys.executable, "-c", "print('must not execute')"]),
            ])
            session = harness.execute(plan)
        self.assertEqual([r.status for r in session.results], ["failed", "skipped"])
        self.assertEqual(session.termination_reason, "wall_time_budget_exhausted")


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest required for actual test-only replay")
class ReviewCliBoundaryTests(unittest.TestCase):
    def execute(self, source, *, tool_budget=48):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        root.mkdir()
        _init_repo(root)
        (root / ".gitignore").write_text(
            ".botte-cache/\n.botte-sandbox/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
        (root / "test_fixture.py").write_text(source, encoding="utf-8")
        _run(root, "git", "add", ".")
        _run(root, "git", "commit", "-m", "review fixture")
        manager = WorktreeLeaseManager(root)
        author = manager.create("author", ttl_seconds=300)
        mission = _mission(budgets={**_mission()["budgets"], "max_tool_calls": tool_budget})
        handoff = build_handoff(
            mission, attempt_id="fixture", worker_id="author", status="READY_FOR_REVIEW",
            workspace_lease=author.contract_view(), checks=[check()],
            evidence_refs=["tests:project"], next_safe_action="Independent review.",
        )
        mission_path = Path(temporary.name) / "mission.json"
        handoff_path = Path(temporary.name) / "handoff.json"
        mission_path.write_text(json.dumps(mission), encoding="utf-8")
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        output = io.StringIO()
        errors = io.StringIO()
        with patch.dict("os.environ", {"BOTTE_NN_AUTO_LABELS": "0"}), redirect_stdout(output), redirect_stderr(errors):
            code = review_cli([str(mission_path), str(handoff_path), "--project", str(root)])
        manager.release(author)
        return code, output.getvalue(), errors.getvalue(), root

    def test_actual_cli_accepts_clean_replay(self):
        code, output, errors, _ = self.execute("def test_ok():\n    assert 2 + 2 == 4\n")
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["verdict"], "ACCEPT")

    def test_actual_cli_refuses_code_changed_during_replay(self):
        code, _, errors, root = self.execute(
            "from pathlib import Path\ndef test_mutates():\n"
            "    Path('README.md').write_text('changed', encoding='utf-8')\n")
        self.assertEqual(code, 2)
        self.assertIn("review worktree changed", errors)
        self.assertIsNone(CheckpointRegistry(root).load("reliable-run-pilot")["best_known_green"])
        self.assertTrue(any(lease.state == "QUARANTINED" for lease in WorktreeLeaseManager(root).list()))

    def test_actual_cli_respects_zero_tool_budget(self):
        code, output, _, _ = self.execute("def test_should_not_run():\n    assert False\n", tool_budget=0)
        self.assertEqual(code, 2)
        packet = json.loads(output)
        self.assertEqual(packet["verdict"], "BLOCKED")
        self.assertEqual([c["status"] for c in packet["replayed_checks"]], ["SKIPPED"])


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__, fromlist=["*"]))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"RESULT: {result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
