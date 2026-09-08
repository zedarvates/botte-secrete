"""Exercise mission authority, context and commit boundaries with real worktrees."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skills.meta_harness import MetaHarness, PipelinePlan, Step
from skills.meta_harness.orchestrator import _AGENT_CATALOG
from skills.meta_harness.lease import WorktreeLeaseManager
from skills.meta_harness.test_reliable_run import _init_repo, _mission, _run
from skills.run_contract import (
    ContractError, build_handoff, compile_context_manifest, contract_fingerprint,
    resume_base_ref,
)
from skills.safe_exit import SafeExitConfig


class MissionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        _init_repo(self.root)
        self.command = [sys.executable, "-c", "print('proof')"]
        self.catalog = {**_AGENT_CATALOG["test"], "command": self.command}
        catalog_patch = patch.dict(_AGENT_CATALOG, {"test": self.catalog})
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)

    def harness(self, **kwargs):
        return MetaHarness(
            self.root, mission=kwargs.pop("mission", _mission()),
            workspace_root=Path(self.tmp.name) / "worktrees", **kwargs,
        )

    def assert_rejected(self, step):
        harness = self.harness()
        with self.assertRaises(ValueError):
            harness.execute(PipelinePlan("untrusted", [step]))
        self.assertIsNone(harness.workspace_lease)

    def test_manual_unknown_command_is_rejected_before_lease(self):
        self.assert_rejected(Step("unregistered", self.command, evidence_ref="tests:project"))

    def test_catalog_name_cannot_disguise_another_command(self):
        self.assert_rejected(Step("test", [sys.executable, "-c", "print('other')"],
                                  evidence_ref="tests:project"))

    def test_catalog_command_cannot_receive_unregistered_arguments(self):
        self.assert_rejected(Step("test", self.command, args=["injected"],
                                  evidence_ref="tests:project"))

    def test_mutating_flag_cannot_be_forged(self):
        info = _AGENT_CATALOG["aramis"]
        self.assert_rejected(Step("aramis", list(info["command"]), mutating=False,
                                  evidence_ref=info["evidence_ref"]))

    def test_direct_mutating_plan_still_requires_act(self):
        info = _AGENT_CATALOG["aramis"]
        self.assert_rejected(Step("aramis", list(info["command"]), mutating=True,
                                  evidence_ref=info["evidence_ref"]))

    def test_plan_mutated_after_planning_is_rejected(self):
        harness = self.harness()
        plan = harness.plan(["test"])
        plan.steps[0].command = [sys.executable, "-c", "print('changed')"]
        with self.assertRaises(ValueError):
            harness.execute(plan)
        self.assertIsNone(harness.workspace_lease)

    def test_forged_evidence_dependencies_or_status_are_rejected(self):
        for field, value in (("evidence_ref", "audit:security"), ("requires", ["fake"]),
                             ("status", "passed")):
            with self.subTest(field=field):
                step = Step("test", self.command, evidence_ref="tests:project")
                setattr(step, field, value)
                self.assert_rejected(step)

    def test_missing_manifest_is_compiled_from_leased_checkout(self):
        harness = self.harness()
        session = harness.execute(harness.plan(["test"]))
        self.assertEqual(session.handoff["status"], "READY_FOR_REVIEW")
        expected = compile_context_manifest(
            harness.workspace_lease.workspace_path, _mission(),
            generated_at=harness.context_manifest["generated_at"],
        )
        self.assertEqual(harness.context_manifest, expected)
        self.assertEqual(session.context_manifest_sha256, expected["manifest_sha256"])

    def test_forged_or_empty_manifest_is_rejected_before_dispatch(self):
        for manifest in ({}, {"manifest_sha256": "f" * 64}):
            with self.subTest(manifest=manifest):
                harness = self.harness(context_manifest=manifest)
                with self.assertRaises(ContractError):
                    harness.execute(harness.plan(["test"]))
                self.assertFalse(harness.session.results)
                self.assertEqual(harness.lease_manager.list()[0].state, "RELEASED")

    def test_rehashed_tampered_context_is_rejected(self):
        original = compile_context_manifest(self.root, _mission())
        for field, value in (("entries", original["entries"][1:]),
                             ("mission_id", "other"), ("total_tokens_est", 0),
                             ("safety_rules_pinned", False), ("raw_content_stored", True)):
            with self.subTest(field=field):
                manifest = copy.deepcopy(original)
                manifest[field] = value
                manifest.pop("manifest_sha256")
                manifest["manifest_sha256"] = contract_fingerprint(manifest)
                harness = self.harness(context_manifest=manifest)
                with self.assertRaises(ContractError):
                    harness.execute(harness.plan(["test"]))
                self.assertFalse(harness.session.results)

    def test_manifest_for_another_mission_is_rejected(self):
        manifest = compile_context_manifest(self.root, _mission(objective="Different work"))
        harness = self.harness(context_manifest=manifest)
        with self.assertRaises(ContractError):
            harness.execute(harness.plan(["test"]))

    def test_manifest_for_dirty_original_checkout_is_rejected(self):
        (self.root / "README.md").write_text("uncommitted context", encoding="utf-8")
        harness = self.harness(context_manifest=compile_context_manifest(self.root, _mission()))
        with self.assertRaises(ContractError):
            harness.execute(harness.plan(["test"]))

    def test_requested_base_ref_determines_compiled_context(self):
        base = _run(self.root, "git", "rev-parse", "HEAD")
        (self.root / "README.md").write_text("newer context", encoding="utf-8")
        _run(self.root, "git", "add", "README.md")
        _run(self.root, "git", "commit", "-m", "new context")
        harness = self.harness(base_ref=base)
        harness.execute(harness.plan(["test"]))
        entry = next(e for e in harness.context_manifest["entries"] if e["path"] == "README.md")
        self.assertEqual(entry["sha256"], hashlib.sha256(b"fixture").hexdigest())

    def test_dirty_author_never_becomes_ready_and_is_preserved(self):
        for name in ("README.md", "untracked.txt"):
            with self.subTest(name=name):
                self.catalog["command"] = [sys.executable, "-c",
                    f"from pathlib import Path; Path({name!r}).write_text('edited', encoding='utf-8')"]
                harness = self.harness(mission=_mission(mission_id=f"dirty-{name}"))
                session = harness.execute(harness.plan(["test"]))
                self.assertEqual(session.handoff["status"], "PARTIAL")
                self.assertEqual(session.workspace_lease["state"], "QUARANTINED")
                self.assertIn("uncommitted_workspace", session.handoff["uncertainties"])
                self.assertTrue((Path(harness.workspace_lease.workspace_path) / name).exists())
                with self.assertRaises(ContractError):
                    resume_base_ref(harness.mission, session.handoff)

    def test_valid_supplied_manifest_is_accepted(self):
        manifest = compile_context_manifest(self.root, _mission())
        harness = self.harness(context_manifest=manifest)
        self.assertEqual(harness.execute(harness.plan(["test"])).handoff["status"], "READY_FOR_REVIEW")

    def test_missing_required_context_rejects_before_dispatch(self):
        mission = _mission(context={"budget_tokens": 2000, "required_files": ["missing.md"],
                                    "optional_files": []})
        harness = self.harness(mission=mission)
        with self.assertRaises(ContractError):
            harness.execute(harness.plan(["test"]))
        self.assertFalse(harness.session.results)

    def test_cli_persists_context_from_resumed_commit(self):
        from skills.run_contract.run_cli import main as run_cli

        harness = self.harness()
        session = harness.execute(harness.plan(["test"]))
        prior_path = Path(self.tmp.name) / "handoff.json"
        prior_path.write_text(json.dumps(session.handoff), encoding="utf-8")
        # A fresh clone models resumption without the original process or its
        # checkpoint registry; its newer HEAD must not supply the context.
        clone = Path(self.tmp.name) / "resume-repo"
        _run(Path(self.tmp.name), "git", "clone", str(self.root), str(clone))
        _run(clone, "git", "config", "user.name", "Botte Test")
        _run(clone, "git", "config", "user.email", "botte@example.invalid")
        (clone / "README.md").write_text("newer context", encoding="utf-8")
        _run(clone, "git", "add", "README.md")
        _run(clone, "git", "commit", "-m", "new context")
        mission_path = Path(self.tmp.name) / "mission.json"
        mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            result = run_cli([str(mission_path), "--project", str(clone),
                              "--resume", str(prior_path), "--plan", "test-only",
                              "--attempt-id", "resumed", "--format", "json"])
        self.assertEqual(result, 0)
        manifest_path, = (clone / ".botte-cache" / "runs").glob("*/resumed/context-manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(e for e in manifest["entries"] if e["path"] == "README.md")
        self.assertEqual(entry["sha256"], hashlib.sha256(b"fixture").hexdigest())

    def test_dirty_fingerprint_binds_content_even_when_status_does_not_change(self):
        manager = WorktreeLeaseManager(self.root, workspace_root=Path(self.tmp.name) / "leases")
        lease = manager.create("fingerprint")
        for name in ("README.md", "untracked.txt"):
            with self.subTest(name=name):
                path = Path(lease.workspace_path) / name
                path.write_text("first", encoding="utf-8")
                first = manager.refresh(lease).dirty_tree_sha256
                path.write_text("other", encoding="utf-8")
                self.assertNotEqual(first, manager.refresh(lease).dirty_tree_sha256)

    def test_untracked_symlink_fingerprint_does_not_read_external_content(self):
        outside = Path(self.tmp.name) / "outside"
        outside.write_text("first", encoding="utf-8")
        manager = WorktreeLeaseManager(self.root, workspace_root=Path(self.tmp.name) / "leases")
        lease = manager.create("symlink")
        (Path(lease.workspace_path) / "link").symlink_to(outside)
        first = manager.refresh(lease).dirty_tree_sha256
        outside.write_text("changed", encoding="utf-8")
        self.assertEqual(first, manager.refresh(lease).dirty_tree_sha256)

    def test_staged_fingerprint_binds_content(self):
        manager = WorktreeLeaseManager(self.root, workspace_root=Path(self.tmp.name) / "leases")
        lease = manager.create("staged")
        workspace = Path(lease.workspace_path)
        (workspace / "README.md").write_text("first", encoding="utf-8")
        _run(workspace, "git", "add", "README.md")
        first = manager.refresh(lease).dirty_tree_sha256
        (workspace / "README.md").write_text("other", encoding="utf-8")
        _run(workspace, "git", "add", "README.md")
        self.assertNotEqual(first, manager.refresh(lease).dirty_tree_sha256)

    def test_quarantined_lease_cannot_claim_ready(self):
        manager = WorktreeLeaseManager(self.root, workspace_root=Path(self.tmp.name) / "leases")
        lease = manager.quarantine(manager.create("author"))
        with self.assertRaises(ContractError):
            build_handoff(_mission(), attempt_id="attempt", worker_id="author",
                status="READY_FOR_REVIEW", workspace_lease=lease.contract_view(),
                checks=[{"name": "test", "status": "PASS", "evidence_ref": "tests:project"}],
                evidence_refs=["tests:project"], next_safe_action="Review")

    def test_explicit_safe_exit_config_cannot_expand_mission_budgets(self):
        mission = _mission()
        mission["budgets"].update(max_iterations=2, max_tool_calls=0, max_wall_seconds=1)
        harness = self.harness(mission=mission, safe_exit_config=SafeExitConfig())
        self.assertEqual(harness.safe_exit_config.max_iterations, 2)
        self.assertEqual(harness.safe_exit_config.max_wall_seconds, 1)
        session = harness.execute(harness.plan(["test"]))
        self.assertEqual(session.handoff["status"], "UNCERTAIN")
        self.assertEqual(session.results[0].status, "skipped")

    def test_stricter_explicit_budget_is_preserved(self):
        harness = self.harness(safe_exit_config=SafeExitConfig(max_tool_calls=0))
        session = harness.execute(harness.plan(["test"]))
        self.assertEqual(session.results[0].status, "skipped")


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MissionBoundaryTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len({getattr(test, "test_case", test).id()
                  for test, _ in result.failures + result.errors})
    skipped = len(result.skipped)
    print(f"RESULT: {result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
