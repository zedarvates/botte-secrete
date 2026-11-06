"""Mission coverage, external trust, revision and review-state regressions."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skills.completion_proof.cli import main as cli
from skills.completion_proof.mission import criterion_witness_digest, verify_mission


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "input.json").write_text('{"value":42}\n', encoding="utf-8")
        (self.source / "check.py").write_text(
            "import json, pathlib, unittest\n"
            "class Check(unittest.TestCase):\n"
            " def test_input(self):\n"
            "  self.assertEqual(json.loads(pathlib.Path('input.json').read_text(encoding='utf-8'))['value'],42)\n",
            encoding="utf-8")
        (self.root / "brief.txt").write_text("Review revision abc: expected input value is 42.\n", encoding="utf-8")
        (self.root / "review.txt").write_text("No blocking finding on revision abc.\n", encoding="utf-8")
        (self.root / "log.txt").write_text("retained test output\n", encoding="utf-8")
        self.contract = {
            "schema": "botte.verified-mission/v1", "mission_id": "task-7", "revision": "abc",
            "input": {"path": "input.json", "sha256": sha(self.source / "input.json")},
            "verifier": {"id": "example.check", "version": "1", "path": "check.py",
                         "sha256": sha(self.source / "check.py")},
            "criteria": [{"id": "input-value", "description": "The supplied value is 42"}],
            "review": {"required": True, "implementer_id": "implementer",
                       "brief_sha256": sha(self.root / "brief.txt")}}
        self.dump("contract.json", self.contract)
        self.contract_pin = sha(self.root / "contract.json")
        self.binding = {"contract_sha256": self.contract_pin, "mission_id": "task-7",
                        "revision": "abc", "input_sha256": self.contract["input"]["sha256"],
                        "verifier": {"id": "example.check", "version": "1"}}
        self.receipt = {
            "schema_version": 1, "run_id": "run-7", "result": {
                "exit_code": 0, "tests_run": 1, "failures": 0, "errors": 0},
            "log": {"path": "log.txt", "sha256": sha(self.root / "log.txt")},
            "sources": [{"path": name, "sha256": sha(self.source / name)}
                        for name in ("input.json", "check.py")]}
        self.dump("receipt.json", self.receipt)
        self.dump("test-report.json", {"status": "complete", "run_id": "run-7",
                                      "proof": {"receipt_ref": "receipt.json"}})
        self.witness = {"schema": "botte.mission-criterion/v1",
                        "binding": dict(self.binding, criterion_id="input-value"),
                        "report_ref": "test-report.json", "receipt_sha256": sha(self.root / "receipt.json")}
        self.review = {"schema": "botte.mission-review/v1", "binding": self.binding.copy(),
                       "reviewer_id": "reviewer", "state": "completed", "decision": "accepted",
                       "brief": {"path": "brief.txt", "sha256": sha(self.root / "brief.txt")},
                       "output": {"path": "review.txt", "sha256": sha(self.root / "review.txt")}}
        self.claim = {"schema": "botte.mission-completion/v1", "status": "complete",
                      "mission_id": "task-7", "contract_sha256": self.contract_pin,
                      "criteria": [{"id": "input-value", "witness_ref": "criterion.json"}],
                      "review_ref": "review.json"}
        self.save()

    def dump(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def save(self):
        self.dump("claim.json", self.claim)
        self.dump("criterion.json", self.witness)
        self.review.setdefault("criteria_sha256", criterion_witness_digest(
            {"input-value": sha(self.root / "criterion.json")}))
        self.dump("review.json", self.review)
        self.pins = {name: sha(self.root / name) for name in ("criterion.json", "review.json")}
        self.dump("pins.json", self.pins)

    def verify(self, **kwargs):
        return verify_mission(self.root / "claim.json", contract=self.root / "contract.json",
                              evidence_root=self.root, source_root=self.source,
                              trusted_contract_sha256=kwargs.get("contract_pin", self.contract_pin),
                              trusted_witnesses=kwargs.get("pins", self.pins))

    def rejected(self, code):
        result = self.verify()
        self.assertFalse(result["verified"], result)
        self.assertIn(code, result["errors"])
        return result

    def test_valid_mission_reuses_v1_verifier(self):
        result = self.verify()
        self.assertTrue(result["verified"], result)
        self.assertEqual(result["status"], "verified_on_mission_criteria")
        self.assertFalse(result["authorizes_task_transition"])
        self.assertTrue(result["criteria"][0]["verification"]["verified"])

    def test_missing_criterion_is_not_completed(self):
        self.claim["criteria"] = []
        self.save()
        self.rejected("criterion_coverage_mismatch")

    def test_added_or_duplicate_criterion_is_rejected(self):
        for identity in ("unrequested", "input-value"):
            self.claim["criteria"] = [{"id": "input-value", "witness_ref": "criterion.json"},
                                      {"id": identity, "witness_ref": "criterion.json"}]
            self.save()
            self.assertFalse(self.verify()["verified"])

    def test_report_cannot_supply_its_own_witness_pin(self):
        original = self.pins.copy()
        self.witness["binding"]["revision"] = "different"
        self.save()
        result = self.verify(pins=original)
        self.assertEqual(result["errors"], ["witness_hash_mismatch"])

    def test_missing_external_witness_pin(self):
        self.assertEqual(self.verify(pins={"review.json": self.pins["review.json"]})["errors"],
                         ["missing_witness_pin"])

    def test_contract_cannot_be_replaced(self):
        self.contract["criteria"] = []
        self.dump("contract.json", self.contract)
        self.rejected("contract_hash_mismatch")

    def test_old_revision_or_wrong_task_or_verifier_is_rejected(self):
        original = self.witness["binding"].copy()
        for key, value in (("revision", "old"), ("mission_id", "other"),
                           ("verifier", {"id": "other", "version": "1"}),
                           ("input_sha256", "0" * 64), ("criterion_id", "other")):
            self.witness["binding"] = dict(original, **{key: value})
            self.save()
            self.rejected("criterion_scope_mismatch")

    def test_changed_input_or_verifier_is_rejected(self):
        for name in ("input.json", "check.py"):
            original = (self.source / name).read_bytes()
            (self.source / name).write_text("changed", encoding="utf-8")
            self.rejected("mission_file_hash_mismatch")
            (self.source / name).write_bytes(original)

    def test_omitted_input_from_test_scope_is_rejected(self):
        self.receipt["sources"] = self.receipt["sources"][1:]
        self.dump("receipt.json", self.receipt)
        self.witness["receipt_sha256"] = sha(self.root / "receipt.json")
        self.save()
        self.rejected("criterion_source_scope_missing")

    def test_passing_claim_does_not_hide_test_failure(self):
        self.receipt["result"].update(exit_code=1, failures=1)
        self.dump("receipt.json", self.receipt)
        self.witness["receipt_sha256"] = sha(self.root / "receipt.json")
        self.save()
        self.assertEqual(self.rejected("criterion_not_verified")["status"], "test_failed")

    def test_missing_review_is_not_completed(self):
        self.claim["review_ref"] = None
        self.save()
        self.rejected("missing_review")

    def test_failed_quota_requested_running_unknown_review_are_incomplete(self):
        for state in ("requested", "running", "failed", "interrupted", "quota_exhausted",
                      "quota_exceeded", "cancelled", "timed_out", "unknown"):
            self.review["state"] = state
            self.save()
            result = self.rejected("review_incomplete")
            self.assertEqual(result["review_state"], state)
            self.assertEqual(result["status"], "review_incomplete")

    def test_review_requires_acceptance_and_other_identity(self):
        self.review["decision"] = "changes_requested"
        self.save()
        self.rejected("review_not_accepted")
        self.review.update(decision="accepted", reviewer_id="implementer")
        self.save()
        self.rejected("same_reviewer_as_implementer")

    def test_review_must_match_exact_revision_and_brief(self):
        self.review["binding"]["revision"] = "other"
        self.save()
        self.rejected("review_scope_mismatch")
        self.review["binding"] = self.binding.copy()
        (self.root / "other-brief.txt").write_text("Please approve this diff.\n", encoding="utf-8")
        self.review["brief"] = {"path": "other-brief.txt", "sha256": sha(self.root / "other-brief.txt")}
        self.save()
        self.rejected("review_brief_mismatch")

    def test_new_criterion_receipt_invalidates_old_review(self):
        self.receipt["run_id"] = "run-8"
        self.dump("receipt.json", self.receipt)
        self.dump("test-report.json", {"status": "complete", "run_id": "run-8",
                                      "proof": {"receipt_ref": "receipt.json"}})
        self.witness["receipt_sha256"] = sha(self.root / "receipt.json")
        self.save()
        self.rejected("review_criteria_mismatch")

    def test_review_output_must_exist_and_match_pin(self):
        (self.root / "review.txt").write_text("", encoding="utf-8")
        self.rejected("mission_file_hash_mismatch")
        self.review["output"]["sha256"] = sha(self.root / "review.txt")
        self.save()
        self.rejected("empty_review_output")

    def test_closed_schema_and_unsafe_path_fail(self):
        self.claim["verified"] = True
        self.save()
        self.rejected("invalid_mission_claim")
        del self.claim["verified"]
        self.witness["report_ref"] = "../outside"
        self.save()
        self.rejected("unsafe_reference")

    def test_real_check_then_mutated_source(self):
        run = subprocess.run([sys.executable, "-m", "unittest", "-v", "check"],
                             cwd=self.source, capture_output=True, text=True,
                             encoding="utf-8", timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("Ran 1 test", run.stderr)
        (self.root / "log.txt").write_text(run.stdout + run.stderr, encoding="utf-8")
        self.receipt["log"]["sha256"] = sha(self.root / "log.txt")
        self.dump("receipt.json", self.receipt)
        self.witness["receipt_sha256"] = sha(self.root / "receipt.json")
        self.save()
        self.review["criteria_sha256"] = criterion_witness_digest(
            {"input-value": sha(self.root / "criterion.json")})
        self.save()
        self.assertTrue(self.verify()["verified"])
        (self.source / "input.json").write_text('{"value":43}', encoding="utf-8")
        self.rejected("mission_file_hash_mismatch")

    def args(self):
        return [str(self.root / "claim.json"), "--verify", "--strict", "--json",
                "--evidence-root", str(self.root), "--source-root", str(self.source),
                "--mission-contract", str(self.root / "contract.json"),
                "--mission-sha256", self.contract_pin, "--mission-pins", str(self.root / "pins.json")]

    def test_actual_cli_strict_gate_and_quota_exit(self):
        for state, expected in (("completed", 0), ("quota_exceeded", 8)):
            self.review["state"] = state
            self.save()
            run = subprocess.run([sys.executable, "-m", "skills.completion_proof.cli"] + self.args(),
                                 capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(run.returncode, expected, run.stderr)
            self.assertEqual(json.loads(run.stdout)["verified"], expected == 0)

    def test_cli_rejects_missing_or_confused_trust_arguments(self):
        for extra in (("--mission-contract", str(self.root / "contract.json")),
                      tuple(self.args()[1:] + ["--receipt-sha256", "0" * 64])):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli([str(self.root / "claim.json")] + list(extra))


if __name__ == "__main__":
    unittest.main()
