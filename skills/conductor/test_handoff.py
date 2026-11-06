"""Content bindings and side-effect boundaries for prepared plan handoffs."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from skills.conductor.handoff import (
    HANDOFF_SCHEMA, MAX_HANDOFF_BYTES, prepare_plan_handoff,
    validate_plan_handoff,
)
from skills.conductor.preferences import METRICS, REQUEST_SCHEMA, propose_plans
from skills.conductor.selection import select_plan
from skills.conductor.verified import MAX_DOCUMENT, execute_verified, validate_plan


def _request():
    return {
        "schema": REQUEST_SCHEMA,
        "currency": "EUR",
        "projects": [{"id": "demo", "goals": ["done"]}],
        "actions": [
            {"id": aid, "needs": needs, "projects": ["demo"],
             "metrics": {metric: 1 for metric in METRICS},
             "provenance": {"kind": "estimate", "ref": "synthetic-fixture"}}
            for aid, needs in (("prepare", []), ("inspect", []),
                               ("deliver", ["prepare"]))
        ],
        "candidates": [{"id": "chosen", "steps": ["prepare", "inspect", "deliver"],
                        "goals": {"demo": ["done"]}}],
        "preferences": {"priorities": [{"metric": "elapsed_minutes"}]},
    }


def _selection(request):
    return select_plan(request, "chosen", propose_plans(request)["input_digest"])


def _plan(request):
    actions = {action["id"]: action for action in request["actions"]}
    return {
        "schema": "botte.skill-plan/v1",
        "goal": "Declared demonstration goal",
        "context": "synthetic-toolchain-v1",
        "steps": [
            {"id": aid, "capability": "synthetic-fixture",
             "command": "python -c \"raise SystemExit(99)\"", "local": True,
             "needs": list(actions[aid]["needs"]),
             "requires": [{"kind": "file_exists", "path": "input.json"}],
             "ensures": [{"kind": "json_equals", "path": "result.json",
                          "pointer": "/ready", "value": True}],
             "observes": ["result.json", "other.txt"],
             "source_hashes": {"worker.py": "0" * 64},
             "effects_before": {"declared": [True, 1, 1.0, None]}}
            for aid in request["candidates"][0]["steps"]
        ],
    }


def _digest(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PlanHandoffTests(unittest.TestCase):
    def setUp(self):
        self.request = _request()
        self.receipt = _selection(self.request)
        self.plan = _plan(self.request)

    def prepare(self, plan=None):
        return prepare_plan_handoff(
            self.request, self.receipt, self.plan if plan is None else plan,
        )

    def test_preserves_intact_plan_and_existing_validator_accepts_it(self):
        handoff = self.prepare()
        self.assertEqual(handoff["schema"], HANDOFF_SCHEMA)
        self.assertEqual(handoff["status"], "prepared_unverified")
        self.assertIs(handoff["execution_authorized"], False)
        self.assertEqual(handoff["execution_plan"], self.plan)
        self.assertEqual(handoff["selection_receipt"], self.receipt)
        self.assertGreaterEqual(len(handoff["limitations"]), 5)
        validate_plan(handoff["execution_plan"])
        self.assertEqual(validate_plan_handoff(self.request, handoff), handoff)

    def test_ids_are_reproducible_and_bind_the_complete_supplied_plan(self):
        original = self.prepare()
        self.assertEqual(original, self.prepare())
        self.assertEqual(original["execution_plan_sha256"], _digest(self.plan))
        body = {key: value for key, value in original.items() if key != "handoff_id"}
        self.assertEqual(original["handoff_id"], _digest(body))
        for key in ("command", "requires", "ensures", "source_hashes", "effects_before"):
            changed = deepcopy(self.plan)
            if key == "command":
                changed["steps"][0][key] = "python other.py"
            elif key == "source_hashes":
                changed["steps"][0][key]["worker.py"] = "1" * 64
            elif key == "effects_before":
                changed["steps"][0][key]["declared"][0] = False
            else:
                changed["steps"][0][key] = []
            with self.subTest(field=key):
                result = self.prepare(changed)
                self.assertNotEqual(result["execution_plan_sha256"], original["execution_plan_sha256"])
                self.assertNotEqual(result["handoff_id"], original["handoff_id"])

    def test_rejects_different_valid_step_order(self):
        self.plan["steps"][:2] = reversed(self.plan["steps"][:2])
        validate_plan(self.plan)
        with self.assertRaisesRegex(ValueError, "IDs and order"):
            self.prepare()

    def test_rejects_missing_additional_and_duplicate_steps(self):
        for mode in ("missing", "additional", "duplicate"):
            plan = deepcopy(self.plan)
            if mode == "missing":
                plan["steps"].pop()
            else:
                step = deepcopy(plan["steps"][0])
                if mode == "additional":
                    step["id"] = "unselected"
                plan["steps"].append(step)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.prepare(plan)

    def test_rejects_removed_and_added_action_dependencies(self):
        for needs in ([], ["prepare", "inspect"]):
            plan = deepcopy(self.plan)
            plan["steps"][-1]["needs"] = needs
            validate_plan(plan)
            with self.subTest(needs=needs), self.assertRaisesRegex(ValueError, "dependencies"):
                self.prepare(plan)

    def test_dependency_membership_is_set_like_without_rewriting_order(self):
        self.request["actions"][-1]["needs"] = ["prepare", "inspect"]
        self.receipt = _selection(self.request)
        self.plan["steps"][-1]["needs"] = ["inspect", "prepare"]
        handoff = self.prepare()
        self.assertEqual(handoff["execution_plan"]["steps"][-1]["needs"], ["inspect", "prepare"])

    def test_rejects_altered_selection_receipt(self):
        for field, value in (("selection_id", "f" * 64),
                             ("execution_authorized", True),
                             ("execution_authorized", 0),
                             ("selected_candidate_id", "other")):
            receipt = deepcopy(self.receipt)
            receipt[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                prepare_plan_handoff(self.request, receipt, self.plan)

    def test_rejects_stale_request_and_now_unavailable_choice(self):
        for mutation in ("cost", "budget", "goal"):
            request = deepcopy(self.request)
            if mutation == "cost":
                request["actions"][0]["metrics"]["money"] = 2
            elif mutation == "budget":
                request["preferences"]["limits"] = {"money": 0}
            else:
                request["projects"][0]["goals"].append("new-goal")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prepare_plan_handoff(request, self.receipt, self.plan)

    def test_packet_validation_rejects_tampering_versions_and_unknown_fields(self):
        original = self.prepare()
        changes = {
            "schema": "parcimonia.plan-handoff/v2", "status": "verified",
            "input_digest": "f" * 64, "selected_candidate_id": "other",
            "execution_plan_sha256": "f" * 64, "handoff_id": "f" * 64,
            "execution_authorized": 0, "limitations": [], "extra": True,
        }
        for field, value in changes.items():
            handoff = deepcopy(original)
            handoff[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_plan_handoff(self.request, handoff)
        handoff = deepcopy(original)
        handoff["execution_plan"]["steps"][0]["command"] = "python different.py"
        with self.assertRaises(ValueError):
            validate_plan_handoff(self.request, handoff)

    def test_outputs_and_validation_results_do_not_alias_inputs(self):
        original_request, original_receipt, original_plan = map(
            deepcopy, (self.request, self.receipt, self.plan),
        )
        handoff = self.prepare()
        validated = validate_plan_handoff(self.request, handoff)
        self.assertIsNot(validated, handoff)
        validated["execution_plan"]["steps"][0]["ensures"].clear()
        self.assertTrue(handoff["execution_plan"]["steps"][0]["ensures"])
        handoff["selection_receipt"]["selected_plan"]["steps"].clear()
        handoff["execution_plan"]["steps"][0]["source_hashes"].clear()
        self.assertEqual((self.request, self.receipt, self.plan),
                         (original_request, original_receipt, original_plan))
        fresh = self.prepare()
        self.plan["steps"][0]["command"] = "python changed.py"
        self.receipt["selected_plan"]["steps"].clear()
        self.assertEqual(fresh["execution_plan"], original_plan)
        self.assertEqual(fresh["selection_receipt"], original_receipt)

    def test_dangerous_command_text_is_inert_and_never_classified_or_executed(self):
        self.plan["steps"][0]["command"] = "python -c \"__import__('os').remove('important')\""
        with patch("builtins.open") as opened, \
                patch("pathlib.Path.open") as path_opened, \
                patch("subprocess.run") as run, \
                patch("urllib.request.urlopen") as network, \
                patch("skills.conductor.verified.execute_verified") as execute, \
                patch("skills.conductor.executor.classify") as classify:
            handoff = self.prepare()
            validate_plan_handoff(self.request, handoff)
        for mock in (opened, path_opened, run, network, execute, classify):
            mock.assert_not_called()
        self.assertEqual(handoff["execution_plan"]["steps"][0]["command"],
                         self.plan["steps"][0]["command"])

    def test_rejects_non_json_nonfinite_and_invalid_plan_types_as_value_errors(self):
        for value in (None, False, [], {"schema": "botte.skill-plan/v1"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare_plan_handoff(self.request, self.receipt, value)
        for invalid in (float("nan"), float("inf"), object(), {1: "invalid"}):
            plan = deepcopy(self.plan)
            plan["steps"][0]["effects_before"] = invalid
            with self.subTest(invalid=type(invalid)), self.assertRaises(ValueError):
                self.prepare(plan)
        self.plan["steps"][0]["ensures"][0]["kind"] = []
        with self.assertRaises(ValueError):
            self.prepare()

    def test_rejects_deep_cyclic_and_oversized_execution_plans(self):
        deep = []
        for _ in range(70):
            deep = [deep]
        cyclic = []
        cyclic.append(cyclic)
        for value in (deep, cyclic, "x" * (MAX_DOCUMENT + 1)):
            plan = deepcopy(self.plan)
            plan["steps"][0]["effects_before"] = value
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                self.prepare(plan)

    def test_rejects_malformed_nonfinite_and_oversized_packets(self):
        for value in (None, False, [], {}, {"schema": HANDOFF_SCHEMA}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan_handoff(self.request, value)
        for value in (float("nan"), "x" * (MAX_HANDOFF_BYTES + 1)):
            handoff = self.prepare()
            handoff["extra"] = value
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                validate_plan_handoff(self.request, handoff)

    def test_cannot_coerce_boolean_predicate_values_to_numbers_in_a_packet(self):
        handoff = self.prepare()
        handoff["execution_plan"]["steps"][0]["ensures"][0]["value"] = 1
        with self.assertRaises(ValueError):
            validate_plan_handoff(self.request, handoff)

    def test_incompatible_parcimonia_action_ids_are_rejected_without_renaming(self):
        self.request["actions"][0]["id"] = "prepare:1"
        self.request["actions"][-1]["needs"] = ["prepare:1"]
        self.request["candidates"][0]["steps"][0] = "prepare:1"
        self.receipt = _selection(self.request)
        self.plan = _plan(self.request)
        before = deepcopy(self.plan)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.plan, before)

    def test_more_than_one_hundred_selected_actions_are_not_split_or_truncated(self):
        action = self.request["actions"][0]
        self.request["actions"] = [dict(deepcopy(action), id=f"a{i}") for i in range(101)]
        self.request["candidates"][0]["steps"] = [a["id"] for a in self.request["actions"]]
        self.receipt = _selection(self.request)
        self.plan = _plan(self.request)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(len(self.plan["steps"]), 101)

    def test_extracted_plan_works_with_existing_dry_run_without_commands_or_checkpoint(self):
        handoff = self.prepare()
        runner = Mock(side_effect=AssertionError("dry run must not dispatch"))
        with tempfile.TemporaryDirectory() as directory:
            report = execute_verified(
                handoff["execution_plan"], cwd=directory, dry_run=True,
                checkpoint="private/run.json", runner=runner,
            )
            self.assertNotIn("error", report)
            self.assertEqual(report["mode"], "dry_run")
            self.assertEqual([row["id"] for row in report["results"]],
                             self.request["candidates"][0]["steps"])
            self.assertFalse(Path(directory, "private").exists())
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
