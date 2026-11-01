"""Behavioural contracts for explicit, non-authorizing plan selections."""

from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy

from skills.conductor.preferences import propose_plans
from skills.conductor.selection import (
    MAX_RECEIPT_BYTES, SELECTION_SCHEMA, select_plan, validate_selection,
)
from skills.conductor.test_preferences import _request


def _select(request=None, candidate_id="economical"):
    request = _request() if request is None else request
    return select_plan(request, candidate_id, propose_plans(request)["input_digest"])


class PlanSelectionTests(unittest.TestCase):
    def test_second_option_is_explicit_choice_and_retains_recommendation(self):
        receipt = _select()
        self.assertEqual(receipt["schema"], SELECTION_SCHEMA)
        self.assertEqual(receipt["selected_candidate_id"], "economical")
        self.assertEqual(receipt["recommended_candidate_id"], "rapid")
        self.assertEqual(receipt["selected_plan"]["steps"],
                         ["shared", "cheap-demo", "cheap-plugin"])
        self.assertEqual(receipt["selected_plan"]["totals"]["money"], 1)
        self.assertEqual(receipt["selected_plan"]["project_totals"]["plugin"]["elapsed_minutes"], 32)
        self.assertEqual(receipt["currency"], "EUR")

    def test_dominated_eligible_option_still_selectable(self):
        request = _request()
        request["preferences"]["priorities"] = [{"metric": "elapsed_minutes"}]
        proposals = propose_plans(request)
        option = next(item for item in proposals["options"] if item["candidate_id"] == "economical")
        self.assertFalse(option["pareto"])
        self.assertEqual(_select(request)["selected_candidate_id"], "economical")

    def test_choice_declaration_never_grants_execution_or_proves_authority(self):
        receipt = _select()
        self.assertEqual(receipt["selection_status"], "selected")
        self.assertEqual(receipt["choice_origin"], "caller_declared")
        self.assertIs(receipt["execution_authorized"], False)
        self.assertIs(receipt["claim"]["choice_authority_verified"], False)
        self.assertIs(receipt["claim"]["source_verified"], False)
        self.assertEqual(receipt["boundaries"], {
            "models": False, "network": False, "execution": False,
            "collection": False, "storage": False,
        })

    def test_changed_cost_priority_goal_and_step_order_reject_stale_digest(self):
        original = _request()
        old_digest = propose_plans(original)["input_digest"]
        changes = []
        changed = deepcopy(original)
        changed["actions"][0]["metrics"]["money"] += 1
        changes.append(changed)
        changed = deepcopy(original)
        changed["preferences"]["priorities"].reverse()
        changes.append(changed)
        changed = deepcopy(original)
        changed["projects"][0]["goals"].append("documented")
        changes.append(changed)
        changed = deepcopy(original)
        changed["candidates"][1]["steps"] = ["shared", "cheap-plugin", "cheap-demo"]
        changes.append(changed)
        for changed in changes:
            with self.subTest(request=changed):
                with self.assertRaisesRegex(ValueError, "stale"):
                    select_plan(changed, "economical", old_digest)

    def test_absent_rejected_and_undetermined_candidates_have_no_fallback(self):
        request = _request()
        with self.assertRaisesRegex(ValueError, "not currently eligible"):
            _select(request, "missing")
        request["preferences"]["limits"] = {"money": 3}
        with self.assertRaisesRegex(ValueError, "not currently eligible"):
            _select(request, "rapid")
        request = _request()
        request["actions"][1]["metrics"]["elapsed_minutes"] = None
        with self.assertRaisesRegex(ValueError, "not currently eligible"):
            _select(request, "rapid")

    def test_candidate_id_requires_bounded_ascii_string(self):
        request = _request()
        digest = propose_plans(request)["input_digest"]
        for candidate in (None, True, 0, {}, [], "", "rapid/", "é", "a" * 65):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    select_plan(request, candidate, digest)

    def test_expected_digest_requires_exact_sha256_text(self):
        request = _request()
        digest = propose_plans(request)["input_digest"]
        for supplied in (None, True, 0, {}, [], "", "a" * 63,
                         "a" * 65, "g" * 64, digest.upper(), digest + " "):
            with self.subTest(digest=supplied):
                with self.assertRaises(ValueError):
                    select_plan(request, "rapid", supplied)
        with self.assertRaisesRegex(ValueError, "stale"):
            select_plan(request, "rapid", "0" * 64)

    def test_malformed_requests_and_receipts_raise_value_error(self):
        for request in (None, True, [], {}, {"schema": "unknown"}):
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    select_plan(request, "rapid", "0" * 64)
        for receipt in (None, True, [], {}, {"selected_candidate_id": True},
                        {"selected_candidate_id": "rapid", "input_digest": object()}):
            with self.subTest(receipt=receipt):
                with self.assertRaises(ValueError):
                    validate_selection(_request(), receipt)

    def test_receipt_tampering_cost_id_steps_digest_and_authority_is_rejected(self):
        request = _request()
        original = _select(request)
        mutations = [
            lambda item: item["selected_plan"]["totals"].update(money=0),
            lambda item: item.update(selected_candidate_id="rapid"),
            lambda item: item["selected_plan"]["steps"].reverse(),
            lambda item: item.update(input_digest="0" * 64),
            lambda item: item.update(selection_id="0" * 64),
            lambda item: item.update(recommended_candidate_id="economical"),
            lambda item: item.update(execution_authorized=True),
            lambda item: item["claim"].update(choice_authority_verified=True),
        ]
        for mutate in mutations:
            altered = deepcopy(original)
            mutate(altered)
            with self.subTest(receipt=altered):
                with self.assertRaises(ValueError):
                    validate_selection(request, altered)
        # Rehashing altered content still cannot replace reconstruction.
        altered = deepcopy(original)
        altered["selected_plan"]["totals"]["money"] = 0
        altered.pop("selection_id")
        payload = json.dumps(altered, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        altered["selection_id"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaises(ValueError):
            validate_selection(request, altered)

    def test_additional_missing_and_changed_json_types_are_rejected(self):
        request = _request()
        receipt = _select(request)
        mutations = [
            lambda item: item.update(extra=False),
            lambda item: item["selected_plan"].update(extra=False),
            lambda item: item.pop("choice_origin"),
            lambda item: item.update(execution_authorized=0),
            lambda item: item["selected_plan"]["totals"].update(money=1.0),
            lambda item: item["selected_plan"]["totals"].update(money=True),
        ]
        for mutate in mutations:
            altered = deepcopy(receipt)
            mutate(altered)
            with self.subTest(receipt=altered):
                with self.assertRaises(ValueError):
                    validate_selection(request, altered)

    def test_replay_is_deterministic_and_id_hashes_complete_receipt_content(self):
        request = _request()
        receipt = _select(request)
        self.assertEqual(_select(request), receipt)
        self.assertEqual(validate_selection(request, receipt), receipt)
        hashed = deepcopy(receipt)
        selection_id = hashed.pop("selection_id")
        payload = json.dumps(hashed, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(payload).hexdigest(), selection_id)
        # Anyone can construct the same consistent content; this is not a signature.
        self.assertFalse(receipt["claim"]["choice_authority_verified"])

    def test_set_like_catalogue_order_does_not_change_receipt(self):
        request = _request()
        receipt = _select(request)
        request["projects"].reverse()
        request["actions"].reverse()
        request["candidates"].reverse()
        for action in request["actions"]:
            action["projects"].reverse()
        self.assertEqual(_select(request), receipt)
        self.assertEqual(validate_selection(request, receipt), receipt)

    def test_snapshots_and_validated_results_are_independent_copies(self):
        request = _request()
        before = deepcopy(request)
        receipt = _select(request)
        self.assertEqual(request, before)
        validated = validate_selection(request, receipt)
        validated["selected_plan"]["steps"].clear()
        validated["selected_plan"]["projects"][0]["goals"].append("changed")
        self.assertEqual(receipt, _select(request))
        receipt["selected_plan"]["goals"]["demo"].clear()
        receipt["selected_plan"]["project_totals"]["demo"]["money"] = 99
        self.assertEqual(request, before)
        request["projects"][0]["goals"].append("later")
        self.assertNotIn("later", receipt["selected_plan"]["projects"][0]["goals"])

    def test_unknown_nonrequired_metrics_are_retained_and_receipt_is_bounded(self):
        request = _request()
        request["actions"][1]["metrics"]["energy_wh"] = None
        receipt = _select(request, "rapid")
        self.assertIn({"metric": "energy_wh"}, receipt["selected_plan"]["unknown_metrics"])
        self.assertIsNone(receipt["selected_plan"]["totals"]["energy_wh"])
        self.assertLess(len(json.dumps(receipt).encode("utf-8")), MAX_RECEIPT_BYTES)
        oversized = deepcopy(receipt)
        oversized["extra"] = "x" * MAX_RECEIPT_BYTES
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_selection(request, oversized)
        nested = deepcopy(receipt)
        value = []
        for _ in range(70):
            value = [value]
        nested["extra"] = value
        with self.assertRaises(ValueError):
            validate_selection(request, nested)


if __name__ == "__main__":
    unittest.main()
