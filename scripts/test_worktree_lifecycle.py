"""Real temporary Git repositories exercise read-only cleanup proposals."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from worktree_lifecycle import InspectionError, SCHEMA, _json, inspect_worktrees


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.work = self.root / "finished"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.git(self.root, "init", "-b", "main", str(self.repo))
        self.git(self.repo, "config", "user.name", "Lifecycle test")
        self.git(self.repo, "config", "user.email", "lifecycle@example.invalid")
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git(self.repo, "add", "app.py")
        self.git(self.repo, "commit", "-m", "baseline")
        self.git(self.repo, "worktree", "add", "-b", "done", str(self.work))
        (self.work / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.git(self.work, "add", "app.py")
        self.git(self.work, "commit", "-m", "completed work")
        self.head = self.git(self.work, "rev-parse", "HEAD").strip()
        self.git(self.repo, "merge", "--no-ff", "done", "-m", "integrate completed work")
        self.merge = self.git(self.repo, "rev-parse", "HEAD").strip()
        self.now = datetime(2026, 11, 2, 15, 0, 0, tzinfo=timezone.utc)
        (self.evidence / "log.txt").write_text("one recorded test passed\n", encoding="utf-8")
        self.receipt = {"schema_version": 1, "run_id": "TASK-123",
                        "result": {"exit_code": 0, "tests_run": 1, "failures": 0, "errors": 0},
                        "log": {"path": "log.txt", "sha256": digest(self.evidence / "log.txt")},
                        "sources": [{"path": "app.py", "sha256": digest(self.work / "app.py")}]}
        (self.evidence / "receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        self.claim = {"status": "complete", "run_id": "TASK-123", "proof": {"receipt_ref": "receipt.json"}}
        (self.evidence / "report.json").write_text(json.dumps(self.claim), encoding="utf-8")
        self.record = {"path": str(self.work), "task_id": "TASK-123", "task_state": "accepted",
                       "activity": "idle", "activity_observed_at": "2026-11-02T14:59:30Z",
                       "pull_request": {"url": "https://github.com/example/repo/pull/12",
                                        "state": "merged", "head_sha": self.head, "merge_sha": self.merge},
                       "proof": {"head_sha": self.head, "evidence_root": str(self.evidence),
                                 "report": "report.json",
                                 "trusted_receipt_sha256": digest(self.evidence / "receipt.json")}}

    def git(self, root, *args):
        command = ["git", "-C", str(root), *args]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout

    def inspect(self, records=None):
        return inspect_worktrees(self.repo, "main", {"schema": SCHEMA, "records":
                                 [self.record] if records is None else records}, now=self.now)

    def row(self, report=None):
        report = report or self.inspect()
        return next(row for row in report["worktrees"] if row["path"] == str(self.work))

    def retained(self, reason):
        row = self.row()
        self.assertEqual(row["status"], "retain")
        self.assertIn(reason, row["reasons"])

    def test_clean_integrated_result_is_only_a_non_mutating_owner_review_candidate(self):
        refs = self.git(self.repo, "show-ref")
        files = {str(p.relative_to(self.work)): p.read_bytes() for p in self.work.rglob("*") if p.is_file()}
        report = self.inspect()
        self.assertEqual(self.row(report)["status"], "candidate_for_owner_review")
        self.assertEqual(report["counts"]["candidates"], 1)
        self.assertEqual(report["mutations"], [])
        self.assertFalse(report["deletion_authorized"])
        self.assertEqual(self.row(report)["evidence"]["run_id"], "TASK-123")
        self.assertEqual(self.git(self.repo, "show-ref"), refs)
        self.assertEqual({str(p.relative_to(self.work)): p.read_bytes() for p in self.work.rglob("*") if p.is_file()}, files)

    def test_primary_worktree_is_retained(self):
        row = next(row for row in self.inspect()["worktrees"] if row["path"] == str(self.repo))
        self.assertIn("primary_worktree", row["reasons"])

    def test_dirty_tracked_file_is_retained(self):
        (self.work / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        self.retained("dirty_untracked_or_ignored")

    def test_untracked_file_is_retained(self):
        (self.work / "notes.txt").write_text("keep this", encoding="utf-8")
        self.retained("dirty_untracked_or_ignored")

    def test_ignored_local_configuration_is_retained(self):
        ignore = self.root / "global-ignore"
        ignore.write_text("private-config.env\n", encoding="utf-8")
        self.git(self.repo, "config", "core.excludesFile", str(ignore))
        secret = self.work / "private-config.env"
        secret.write_text("local configuration to preserve\n", encoding="utf-8")
        self.retained("dirty_untracked_or_ignored")
        self.assertTrue(secret.exists())

    def test_unintegrated_commit_is_retained_even_when_record_says_merged(self):
        (self.work / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        self.git(self.work, "add", "app.py")
        self.git(self.work, "commit", "-m", "new local work")
        new_head = self.git(self.work, "rev-parse", "HEAD").strip()
        self.record["pull_request"]["head_sha"] = new_head
        self.record["proof"]["head_sha"] = new_head
        self.retained("commits_not_integrated")

    def test_active_unknown_and_stale_activity_are_retained(self):
        for activity in ("active", "unknown", None):
            self.record["activity"] = activity
            self.retained("active_or_unknown_execution")
        self.record["activity"] = "idle"
        for observed in ("2026-11-02T14:00:00Z", "2026-11-02T16:00:00Z"):
            self.record["activity_observed_at"] = observed
            self.retained("stale_activity_observation")

    def test_missing_provenance_and_unaccepted_mission_are_retained(self):
        self.assertIn("missing_task_provenance", self.row(self.inspect([]))["reasons"])
        self.record["task_state"] = "completed"
        self.retained("task_not_accepted")

    def test_pr_merged_boolean_or_wrong_head_does_not_qualify(self):
        self.record["pull_request"]["state"] = True
        self.retained("pull_request_not_merged")
        self.record["pull_request"]["state"] = "merged"
        self.record["pull_request"]["head_sha"] = "0" * 40
        self.retained("pull_request_head_mismatch")

    def test_nonstring_pr_url_is_retained_without_crashing(self):
        for url in (None, 1, ["https://github.com/example/repo/pull/12"], {"x": 1}):
            self.record["pull_request"]["url"] = url
            self.retained("invalid_pull_request_reference")

    def test_missing_or_tampered_proof_is_retained(self):
        original = deepcopy(self.record["proof"])
        self.record["proof"] = None
        self.retained("missing_or_unbound_result")
        self.record["proof"] = original
        (self.evidence / "log.txt").write_text("modified log", encoding="utf-8")
        self.retained("result_not_verified")

    def test_result_for_another_mission_is_retained(self):
        self.claim["run_id"] = "TASK-OTHER"
        (self.evidence / "report.json").write_text(json.dumps(self.claim), encoding="utf-8")
        self.retained("task_result_mismatch")

    def test_duplicate_record_and_linked_path_are_rejected(self):
        with self.assertRaises(InspectionError):
            self.inspect([self.record, self.record])
        link = self.root / "linked-worktree"
        try:
            link.symlink_to(self.work, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.record["path"] = str(link)
        with self.assertRaises(InspectionError):
            self.inspect()
        self.assertTrue(link.is_symlink())

    def test_report_path_traversal_is_retained(self):
        self.record["proof"]["report"] = "../report.json"
        self.retained("unsafe_report_reference")

    def test_output_limit_is_explicit(self):
        from unittest.mock import patch
        with patch("worktree_lifecycle.MAX_WORKTREES", 1):
            report = self.inspect([])
        self.assertFalse(report["complete"])
        self.assertEqual(report["counts"]["omitted"], 1)

    def test_json_duplicate_keys_and_nonfinite_values_fail(self):
        for data in (b'{"records":[],"records":[]}', b'{"value":NaN}', b'[]'):
            with self.assertRaises(InspectionError):
                _json(data)

    def test_actual_cli_is_read_only_and_invalid_ref_is_blocked(self):
        manifest = self.root / "records.json"
        manifest.write_text(json.dumps({"schema": SCHEMA, "records": []}), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("worktree_lifecycle.py")),
                   "--repo", str(self.repo), "--target", "main", "--records", str(manifest)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "read_only")
        self.assertEqual(report["counts"]["candidates"], 0)
        command[command.index("main")] = "missing-ref"
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")


if __name__ == "__main__":
    program = unittest.main(exit=False)
    result = program.result
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"RESULT: {result.testsRun - failed - skipped} passed, {failed} failed")
    print(f"SKIPPED: {skipped}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
