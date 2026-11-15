"""Remaining-work cost review, actual local evidence and read-only boundaries."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from skills.conductor.handoff import prepare_plan_handoff
from skills.conductor.preferences import METRICS, REQUEST_SCHEMA as PREFERENCES_SCHEMA, propose_plans
from skills.conductor.replanning import (
    MAX_DIAGNOSTICS, MAX_INPUT_BYTES, REQUEST_SCHEMA, RESULT_SCHEMA, review_plan_replanning,
)
from skills.conductor.selection import select_plan
from skills.conductor.verified import MAX_REPORT, RUN_SCHEMA, _digest


def _request():
    return {
        "schema": PREFERENCES_SCHEMA, "currency": "EUR",
        "projects": [{"id": "demo", "goals": ["done"]}],
        "actions": [{"id": aid, "needs": needs, "projects": ["demo"],
                     "metrics": {metric: cost for metric in METRICS},
                     "provenance": {"kind": "estimate", "ref": "synthetic-not-a-benchmark"}}
                    for aid, needs, cost in (("a", [], 10), ("b", ["a"], 2),
                                             ("c", ["b"], 3), ("independent", [], 20))],
        "candidates": [{"id": "chosen", "steps": ["a", "b", "c"], "goals": {"demo": ["done"]}},
                       {"id": "independent", "steps": ["independent"], "goals": {"demo": ["done"]}}],
        "preferences": {"priorities": [{"metric": "money"}, {"metric": "elapsed_minutes"}]},
    }


class ReplanningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.request = _request()
        self.source_digest = hashlib.sha256(b"source-v1").hexdigest()
        self.plan = {"schema": "botte.skill-plan/v1", "goal": "Declared fixture goal",
                     "context": "replanning-fixture-v1", "steps": [
                         {"id": action["id"], "capability": "fixture", "command": "python worker.py",
                          "local": True, "needs": action["needs"],
                          "requires": [{"kind": "text_contains", "path": "input.txt", "value": "ready"}],
                          "ensures": [{"kind": "json_equals", "path": action["id"] + ".json",
                                       "pointer": "/ok", "value": True}],
                          "observes": [action["id"] + ".json"],
                          "source_hashes": {"worker.py": self.source_digest}}
                         for action in self.request["actions"][:3]]}
        for path, value in (("input.txt", "ready"), ("worker.py", "source-v1"),
                            ("a.json", '{"ok":true}'), ("b.json", '{"ok":true}'),
                            ("c.json", '{"ok":true}')):
            self.write(path, value)
        self.rebuild_handoff()
        self.checkpoint = {"schema": RUN_SCHEMA, "run_id": "fixture-run",
                           "plan_sha256": _digest(self.plan),
                           "context_sha256": _digest({"root": str(self.root.resolve()),
                                                       "context": self.plan["context"],
                                                       "python": sys.version, "executable": sys.executable}),
                           "results": [{"id": aid, "status": "verified" if aid == "a" else "blocked",
                                        "started": aid == "a", "exit_code": 0 if aid == "a" else None}
                                       for aid in ("a", "b", "c")]}
        self.save_checkpoint()

    def write(self, path, value):
        (self.root / path).write_text(value, encoding="utf-8")

    def rebuild_handoff(self):
        proposals = propose_plans(self.request)
        selection = select_plan(self.request, "chosen", proposals["input_digest"])
        self.handoff = prepare_plan_handoff(self.request, selection, self.plan)

    def save_checkpoint(self):
        self.write("run.json", json.dumps(self.checkpoint, allow_nan=False))

    def envelope(self, current=None):
        return {"schema": REQUEST_SCHEMA, "previous_request": deepcopy(self.request),
                "previous_handoff": deepcopy(self.handoff),
                "current_request": deepcopy(self.request if current is None else current),
                "budget_scope": "remaining_work"}

    def review(self, envelope=None, path="run.json"):
        return review_plan_replanning(self.envelope() if envelope is None else envelope,
                                      path, cwd=str(self.root))

    def candidate(self, report, cid="chosen"):
        return next(candidate for candidate in report["candidates"] if candidate["id"] == cid)

    def test_reuses_only_verified_evidence_and_preserves_full_order(self):
        result = self.review()
        chosen = self.candidate(result)
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(chosen["reused_action_ids"], ["a"])
        self.assertEqual(chosen["remaining_action_ids"], ["b", "c"])
        self.assertEqual(chosen["incremental_totals"]["money"], 5)
        self.assertTrue(chosen["resume_compatible"])
        self.assertFalse(result["reconciliation_required"])
        self.assertEqual([state["state"] for state in result["step_states"]],
                         ["reusable", "unstarted", "unstarted"])

    def test_priority_cost_and_remaining_caps_can_change_without_sunk_subtraction(self):
        current = deepcopy(self.request)
        current["actions"][0]["metrics"]["money"] = 1000
        current["actions"][1]["metrics"]["money"] = 1
        current["preferences"] = {"priorities": [{"metric": "human_minutes"}], "limits": {"money": 4}}
        result = self.review(self.envelope(current))
        chosen = self.candidate(result)
        self.assertEqual(chosen["status"], "eligible")
        self.assertEqual(chosen["incremental_totals"]["money"], 4)
        self.assertTrue(chosen["resume_compatible"])
        self.assertFalse(result["cost_scope"]["sunk_costs_subtracted"])
        self.assertEqual(result["budget_scope"], "remaining_work")

    def test_keeps_peak_ram_and_unknown_peak_for_reused_actions(self):
        current = deepcopy(self.request)
        current["preferences"]["limits"] = {"peak_ram_gib": 8}
        chosen = self.candidate(self.review(self.envelope(current)))
        self.assertEqual(chosen["incremental_totals"]["peak_ram_gib"], 10)
        self.assertEqual(chosen["status"], "rejected")
        current["actions"][0]["metrics"]["peak_ram_gib"] = None
        chosen = self.candidate(self.review(self.envelope(current)))
        self.assertIsNone(chosen["incremental_totals"]["peak_ram_gib"])
        self.assertEqual(chosen["status"], "undetermined")

    def test_unknown_additive_completed_cost_is_zero_but_unknown_remaining_cost_stays_unknown(self):
        current = deepcopy(self.request)
        current["actions"][0]["metrics"]["money"] = None
        current["actions"][1]["metrics"]["money"] = None
        chosen = self.candidate(self.review(self.envelope(current)))
        self.assertEqual(chosen["reused_action_ids"], ["a"])
        self.assertIsNone(chosen["incremental_totals"]["money"])
        self.assertEqual(chosen["status"], "undetermined")

    def test_completed_project_is_retained_with_zero_additive_future_totals(self):
        self.request["projects"].append({"id": "finished", "goals": ["complete"]})
        self.request["actions"][0]["projects"] = ["finished"]
        self.request["candidates"][0]["goals"]["finished"] = ["complete"]
        self.request["candidates"][1]["goals"]["finished"] = ["complete"]
        self.rebuild_handoff()
        chosen = self.candidate(self.review())
        self.assertEqual(chosen["status"], "eligible")
        self.assertEqual(chosen["incremental_project_totals"]["finished"]["money"], 0)
        self.assertEqual(chosen["incremental_project_totals"]["finished"]["elapsed_minutes"], 0)
        self.assertEqual(chosen["incremental_project_totals"]["finished"]["peak_ram_gib"], 10)

    def test_finished_project_after_unstarted_work_has_zero_remaining_elapsed(self):
        self.request["projects"].append({"id": "finished", "goals": ["complete"]})
        self.request["actions"][1].update(needs=[], projects=["finished"])
        self.plan["steps"][1]["needs"] = []
        self.request["candidates"][0]["goals"]["finished"] = ["complete"]
        self.rebuild_handoff()
        self.checkpoint["plan_sha256"] = _digest(self.plan)
        self.checkpoint["results"][0].update(status="blocked", started=False, exit_code=None)
        self.checkpoint["results"][1].update(status="verified", started=True, exit_code=0)
        self.save_checkpoint()
        current = deepcopy(self.request)
        current["preferences"]["project_limits"] = {"finished": {"elapsed_minutes": 0}}
        original = deepcopy(current)
        chosen = self.candidate(self.review(self.envelope(current)))
        self.assertEqual(chosen["status"], "eligible")
        self.assertEqual(chosen["reused_action_ids"], ["b"])
        self.assertEqual(chosen["remaining_action_ids"], ["a", "c"])
        self.assertEqual(chosen["incremental_project_totals"]["finished"]["elapsed_minutes"], 0)
        self.assertEqual(chosen["incremental_project_totals"]["finished"]["peak_ram_gib"], 2)
        self.assertEqual(chosen["incremental_totals"]["elapsed_minutes"], 13)
        self.assertTrue(chosen["resume_compatible"])
        self.assertEqual(current, original)

    def test_last_remaining_beneficiary_controls_project_elapsed_priority_and_limit(self):
        self.request["projects"].append({"id": "other", "goals": ["complete"]})
        self.request["actions"][1].update(needs=[], projects=["other"])
        self.request["actions"][2]["needs"] = []
        self.plan["steps"][1]["needs"] = []
        self.plan["steps"][2]["needs"] = []
        self.request["candidates"][0]["goals"]["other"] = ["complete"]
        self.request["candidates"].append({"id": "alternative", "steps": ["b", "a", "c"],
                                           "goals": {"demo": ["done"], "other": ["complete"]}})
        self.rebuild_handoff()
        self.checkpoint["plan_sha256"] = _digest(self.plan)
        self.checkpoint["results"][0].update(status="blocked", started=False, exit_code=None)
        self.checkpoint["results"][2].update(status="verified", started=True, exit_code=0)
        self.save_checkpoint()
        current = deepcopy(self.request)
        current["preferences"] = {"priorities": [{"project": "demo", "metric": "elapsed_minutes"}]}
        result = self.review(self.envelope(current))
        self.assertEqual(self.candidate(result)["incremental_project_totals"]["demo"]["elapsed_minutes"], 10)
        self.assertEqual(self.candidate(result, "alternative")["incremental_project_totals"]["demo"]["elapsed_minutes"], 12)
        self.assertEqual(result["recommended_candidate_id"], "chosen")
        current["preferences"]["project_limits"] = {"demo": {"elapsed_minutes": 10}}
        result = self.review(self.envelope(current))
        self.assertEqual(self.candidate(result)["status"], "eligible")
        self.assertEqual(self.candidate(result, "alternative")["status"], "rejected")

    def test_internal_cost_projection_never_repairs_invalid_original_dependency_order(self):
        current = deepcopy(self.request)
        current["candidates"][0]["steps"] = ["b", "a", "c"]
        chosen = self.candidate(self.review(self.envelope(current)))
        self.assertEqual(chosen["status"], "rejected")
        self.assertEqual(chosen["reason_counts"]["dependency_not_preceding"], 1)
        self.assertFalse(chosen["resume_compatible"])
        self.assertEqual(chosen["reused_action_ids"], ["a"])
        self.assertEqual(chosen["remaining_action_ids"], ["b", "c"])

    def test_failed_running_uncertain_unverified_and_stale_never_become_retryable(self):
        for status, code in (("failed", 7), ("running", None), ("uncertain", -1),
                             ("uncertain", 7), ("unverified", 0), ("stale", 0)):
            self.checkpoint["results"][0].update(status=status, started=True, exit_code=code)
            self.save_checkpoint()
            with self.subTest(status=status, code=code):
                result = self.review()
                self.assertTrue(result["reconciliation_required"])
                self.assertEqual(result["step_states"][0]["state"], "reconciliation_required")
                self.assertEqual(self.candidate(result)["status"], "withheld")
                self.assertEqual(self.candidate(result)["execution_status"], "reconciliation_required")
                self.assertEqual(self.candidate(result)["reused_action_ids"], [])
                self.assertEqual(self.candidate(result, "independent")["status"], "eligible")

    def test_unstarted_pending_blocked_skipped_remain_unstarted(self):
        for status in ("pending", "blocked", "skipped"):
            self.checkpoint["results"][1]["status"] = status
            self.save_checkpoint()
            with self.subTest(status=status):
                self.assertEqual(self.review()["step_states"][1]["state"], "unstarted")

    def test_stale_output_precondition_and_source_are_observed_locally(self):
        for path, value, reason in (("a.json", '{"ok":false}', "postconditions_failed"),
                                    ("input.txt", "not available", "preconditions_failed"),
                                    ("worker.py", "changed source", "sources_failed")):
            original = (self.root / path).read_text(encoding="utf-8")
            self.write(path, value)
            with self.subTest(path=path):
                result = self.review()
                self.assertIn(reason, result["step_states"][0]["reasons"])
                self.assertEqual(self.candidate(result)["status"], "withheld")
            self.write(path, original)

    def test_nested_started_dependents_are_stale_and_new_descendants_are_withheld(self):
        for row in self.checkpoint["results"]:
            row.update(status="verified", started=True, exit_code=0)
        self.save_checkpoint()
        self.write("a.json", '{"ok":false}')
        current = deepcopy(self.request)
        current["actions"].append(dict(deepcopy(current["actions"][-1]), id="new", needs=["c"]))
        current["candidates"].append({"id": "descendant", "steps": ["new"], "goals": {"demo": ["done"]}})
        result = self.review(self.envelope(current))
        self.assertEqual(result["reconciliation_action_ids"], ["a", "b", "c"])
        self.assertIn("dependency_not_reusable", result["step_states"][2]["reasons"])
        self.assertEqual(self.candidate(result, "descendant")["status"], "withheld")

    def test_empty_ensures_and_forged_checkpoint_checks_cannot_prove_reuse(self):
        self.plan["steps"][0]["ensures"] = []
        self.rebuild_handoff()
        self.checkpoint["plan_sha256"] = _digest(self.plan)
        self.checkpoint["results"][0]["postcondition_checks"] = [{"passed": True}]
        self.save_checkpoint()
        result = self.review()
        self.assertIn("postconditions_missing", result["step_states"][0]["reasons"])
        self.assertEqual(self.candidate(result)["status"], "withheld")

    def test_changed_started_contract_requires_reconciliation(self):
        for field, value in (("needs", ["independent"]), ("projects", ["other"]),
                             ("provenance", {"kind": "measurement", "ref": "changed"})):
            current = deepcopy(self.request)
            if field == "projects":
                current["projects"].append({"id": "other", "goals": ["done"]})
                for candidate in current["candidates"]:
                    candidate["goals"]["other"] = ["done"]
            current["actions"][0][field] = value
            with self.subTest(field=field):
                result = self.review(self.envelope(current))
                self.assertIn("started_action_contract_changed", result["step_states"][0]["reasons"])
                self.assertFalse(self.candidate(result)["resume_compatible"])
                self.assertEqual(self.candidate(result)["status"], "withheld")

    def test_new_candidates_and_changed_goal_declarations_are_execution_unqualified(self):
        current = deepcopy(self.request)
        current["candidates"].append(dict(deepcopy(current["candidates"][0]), id="other-name"))
        result = self.review(self.envelope(current))
        self.assertTrue(self.candidate(result)["resume_compatible"])
        self.assertEqual(self.candidate(result, "other-name")["execution_status"], "execution_unqualified")
        self.assertEqual(self.candidate(result, "other-name")["reused_action_ids"], ["a"])
        current["projects"][0]["goals"].append("extra")
        for candidate in current["candidates"]:
            candidate["goals"]["demo"].append("extra")
        self.assertFalse(self.candidate(self.review(self.envelope(current)))["resume_compatible"])

    def test_bound_checkpoint_and_handoff_tampering_are_rejected(self):
        original = deepcopy(self.checkpoint)
        for key, value in (("schema", "unknown"), ("plan_sha256", "f" * 64),
                           ("context_sha256", "f" * 64)):
            self.checkpoint = deepcopy(original)
            self.checkpoint[key] = value
            self.save_checkpoint()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.review()
        self.checkpoint = original
        self.save_checkpoint()
        envelope = self.envelope()
        envelope["previous_handoff"]["execution_plan"]["steps"][0]["command"] = "changed"
        with self.assertRaises(ValueError):
            self.review(envelope)

    def test_checkpoint_row_types_order_and_state_consistency_are_strict(self):
        original = deepcopy(self.checkpoint)
        cases = [("status", []), ("status", "pending"), ("started", 1),
                 ("started", False), ("exit_code", False), ("exit_code", None)]
        for field, value in cases:
            self.checkpoint = deepcopy(original)
            self.checkpoint["results"][0][field] = value
            self.save_checkpoint()
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.review()
        self.checkpoint = deepcopy(original)
        self.checkpoint["results"].reverse()
        self.save_checkpoint()
        with self.assertRaises(ValueError):
            self.review()

    def test_rejects_ambiguous_nonfinite_malformed_and_oversized_checkpoint_json(self):
        raw = (self.root / "run.json").read_text(encoding="utf-8")
        for value in ('{"schema":1,"schema":2}', '{"extra":NaN}', '{"extra":1e999}', "{", "[]"):
            self.write("run.json", value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.review()
        self.write("run.json", raw)
        with (self.root / "run.json").open("wb") as stream:
            stream.write(b" " * (MAX_REPORT + 1))
        with self.assertRaises(ValueError):
            self.review()

    def test_checkpoint_paths_are_explicit_project_relative_and_symlink_free(self):
        for path in (None, ".", "../run.json", str(self.root / "run.json"), "C:/run.json", "missing.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.review(path=path)
        (self.root / "linked.json").symlink_to(self.root / "run.json")
        with self.assertRaises(ValueError):
            self.review(path="linked.json")
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.review(path="linked/run.json")

    def test_strict_envelope_schema_budget_scope_json_types_depth_and_size(self):
        for field, value in (("schema", "parcimonia.plan-replanning/v2"),
                             ("budget_scope", "lifetime"), ("extra", True),
                             ("current_request", None), ("current_request", float("nan"))):
            envelope = self.envelope()
            envelope[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.review(envelope)
        for bad in ("x" * (MAX_INPUT_BYTES + 1), object(), {1: "invalid"}):
            envelope = self.envelope()
            envelope["extra"] = bad
            with self.assertRaises(ValueError):
                self.review(envelope)
        deep = []
        for _ in range(70):
            deep = [deep]
        envelope = self.envelope()
        envelope["extra"] = deep
        with self.assertRaises(ValueError):
            self.review(envelope)

    def test_changed_checkpoint_during_checks_returns_no_reuse_certificate(self):
        from skills.conductor import replanning
        original_check = replanning._check

        def mutate(*args):
            self.checkpoint["results"][1]["status"] = "skipped"
            self.save_checkpoint()
            return original_check(*args)

        with patch("skills.conductor.replanning._check", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "checkpoint changed"):
            self.review()

    def test_checkpoint_is_separate_from_observed_resources(self):
        self.plan["steps"][0]["observes"].append("run.json")
        self.rebuild_handoff()
        self.checkpoint["plan_sha256"] = _digest(self.plan)
        self.save_checkpoint()
        with self.assertRaisesRegex(ValueError, "separate"):
            self.review()

    def test_review_never_executes_writes_classifies_or_mutates_inputs(self):
        envelope = self.envelope()
        original = deepcopy(envelope)
        snapshot = {path.name: path.read_bytes() for path in self.root.iterdir()}
        with patch("subprocess.run") as run, \
                patch("skills.conductor.verified.execute_verified") as execute, \
                patch("skills.conductor.verified.write_json") as write, \
                patch("skills.conductor.verified._checkpoint_lock") as lock, \
                patch("skills.conductor.executor.classify") as classify, \
                patch("urllib.request.urlopen") as network:
            result = self.review(envelope)
        for mocked in (run, execute, write, lock, classify, network):
            mocked.assert_not_called()
        self.assertEqual(snapshot, {path.name: path.read_bytes() for path in self.root.iterdir()})
        self.assertEqual(envelope, original)
        self.assertIsNone(result["selected_candidate_id"])
        self.assertFalse(result["execution_authorized"])
        self.assertNotIn("comparison_request", result)
        self.assertNotIn("execution_plan", result)
        self.assertNotIn('"command":', json.dumps(result))
        self.assertNotIn("python worker.py", json.dumps(result))
        self.assertEqual(result["checkpoint_sha256"], hashlib.sha256(snapshot["run.json"]).hexdigest())

    def test_diagnostics_are_bounded_with_complete_counts_and_no_file_content_echo(self):
        self.plan["steps"][0]["requires"] = [
            {"kind": "text_contains", "path": "input.txt", "value": "missing"} for _ in range(100)]
        self.rebuild_handoff()
        self.checkpoint["plan_sha256"] = _digest(self.plan)
        self.save_checkpoint()
        result = self.review()
        self.assertEqual(len(result["diagnostics"]), MAX_DIAGNOSTICS)
        self.assertEqual(result["diagnostic_counts"]["local_check_failed"], 100)
        self.assertEqual(result["diagnostics_omitted"], 37)
        self.assertNotIn("source-v1", json.dumps(result))
        result["candidates"][0]["reused_action_ids"].append("tampered")
        self.assertNotIn("tampered", json.dumps(self.review()))

    def test_dense_goal_rejections_keep_exact_counts_and_bounded_goal_samples(self):
        current = deepcopy(self.request)
        current["projects"] = [{"id": f"p{index:02}", "goals": [f"g{goal:02}" for goal in range(64)]}
                               for index in range(32)]
        current["actions"] = [deepcopy(current["actions"][-1])]
        current["actions"][0]["projects"] = ["p00"]
        current["candidates"] = [{"id": f"dense{index}", "steps": ["independent"], "goals": {}}
                                 for index in range(4)]
        original = deepcopy(current)
        result = self.review(self.envelope(current))
        self.assertEqual(result["detail_caps"]["goals_per_reason"], 8)
        for candidate in result["candidates"]:
            self.assertEqual(candidate["status"], "rejected")
            self.assertEqual(candidate["reason_counts"]["goals_not_declared"], 32)
            self.assertEqual(candidate["reason_counts"]["project_has_no_action"], 31)
            missing = [reason for reason in candidate["reasons"] if reason["code"] == "goals_not_declared"]
            self.assertEqual(len(missing), 32)
            for reason in missing:
                self.assertEqual(reason["goal_count"], 64)
                self.assertEqual(reason["goals_omitted"], 56)
                self.assertEqual(reason["goals"], [f"g{goal:02}" for goal in range(8)])
        self.assertEqual(result["ranking"], [])
        self.assertEqual(current, original)

    def test_all_withheld_candidates_produce_no_recommendation(self):
        current = deepcopy(self.request)
        current["candidates"] = current["candidates"][:1]
        self.write("a.json", '{"ok":false}')
        result = self.review(self.envelope(current))
        self.assertEqual(result["ranking"], [])
        self.assertIsNone(result["recommended_candidate_id"])
        self.assertEqual(self.candidate(result)["status"], "withheld")


if __name__ == "__main__":
    unittest.main()
