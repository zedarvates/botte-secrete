"""Adversarial checks for the offline assessment evaluator and its evidence."""

import copy
from pathlib import Path
import tempfile
import unittest

from skills.preflight.assessment import assess_task
from skills.preflight.evaluation import evaluate, grade_assessment, load_corpus, validate_corpus


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.corpus = load_corpus()
        self.case = self.corpus["cases"][0]
        self.tools = self.corpus["tool_inventories"]["default"]
        self.assessment = assess_task(self.case["task"], self.tools)

    def test_authored_corpus_runs_without_claiming_a_model_evaluation(self):
        result = evaluate(self.corpus)
        self.assertEqual(result["summary"]["total"], len(self.corpus["cases"]))
        self.assertEqual(result["summary"]["failed"], 0)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["model_selection"]["status"], "not_run")
        self.assertEqual(result["model_selection"]["evaluated_cases"], 0)
        for name in ("corpus_sha256", "assessment_sha256", "finder_sha256"):
            self.assertRegex(result["provenance"][name], r"^[0-9a-f]{64}$")
        self.assertTrue(all(value is None for value in result["measured_usage"].values()))

    def test_duplicate_json_keys_are_rejected_before_corpus_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text('{"schema":"first","schema":"second"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_corpus(path)

    def test_duplicate_case_ids_and_unknown_inventories_are_rejected(self):
        for mutation in ("duplicate_id", "unknown_inventory"):
            corpus = copy.deepcopy(self.corpus)
            if mutation == "duplicate_id":
                corpus["cases"][1]["id"] = corpus["cases"][0]["id"]
            else:
                corpus["cases"][0]["tool_inventory"] = "nonexistent"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_corpus(corpus)

    def test_unknown_expectation_fields_cannot_silently_disable_a_check(self):
        corpus = copy.deepcopy(self.corpus)
        corpus["cases"][0]["expect"]["candidate_tools"] = ["compute_statistics"]
        with self.assertRaises(ValueError):
            validate_corpus(corpus)

    def test_unknown_and_duplicate_inventory_tools_are_rejected(self):
        for mutation in ("unknown_expected_tool", "duplicate_offered_tool"):
            corpus = copy.deepcopy(self.corpus)
            if mutation == "unknown_expected_tool":
                corpus["cases"][0]["expect"]["candidate_tool"] = "imaginary"
            else:
                corpus["tool_inventories"]["default"].append(
                    copy.deepcopy(corpus["tool_inventories"]["default"][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_corpus(corpus)

    def test_boolean_budget_and_incoherent_expectations_are_rejected(self):
        for mutation in ("boolean_budget", "forbidden_required_tool", "abstain_with_required_tool"):
            corpus = copy.deepcopy(self.corpus)
            case = corpus["cases"][0]
            if mutation == "boolean_budget":
                case["context_budget"] = True
            elif mutation == "forbidden_required_tool":
                case["expect"]["forbidden_candidate_tools"] = [case["expect"]["candidate_tool"]]
            else:
                case["expect"]["status"] = "abstained"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_corpus(corpus)

    def test_invalid_metadata_and_ineffective_expectations_are_rejected(self):
        for mutation in ("invalid_tool_name", "null_candidate", "vacuous_empty_list"):
            corpus = copy.deepcopy(self.corpus)
            if mutation == "invalid_tool_name":
                corpus["tool_inventories"]["unrelated"][0]["name"] = "invalid tool name"
            elif mutation == "null_candidate":
                corpus["cases"][0]["expect"] = {"candidate_tool": None}
            else:
                corpus["cases"][0]["expect"] = {"reasons_include": []}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_corpus(corpus)

    def test_forged_execution_or_capability_claims_fail_even_with_expected_intent(self):
        for mutation in ("execution", "model_calls", "capability"):
            result = copy.deepcopy(self.assessment)
            if mutation == "execution":
                result["boundaries"]["execution"] = True
            elif mutation == "model_calls":
                result["boundaries"]["model_calls"] = 1
            else:
                result["candidate_tools"][0]["capability_verified"] = True
            with self.subTest(mutation=mutation):
                self.assertTrue(grade_assessment(self.case, result, self.tools))

    def test_forged_candidate_and_wrong_status_fail_despite_expected_tool_presence(self):
        result = copy.deepcopy(self.assessment)
        result["candidate_tools"].append({"name": "invented_tool", "lexical_score": 1.0,
                                          "capability_verified": False})
        self.assertTrue(grade_assessment(self.case, result, self.tools))
        result = copy.deepcopy(self.assessment)
        result["status"] = "abstained"
        self.assertTrue(grade_assessment(self.case, result, self.tools))

    def test_missing_negation_evidence_fails_an_otherwise_correct_abstention(self):
        case = next(case for case in self.corpus["cases"] if case["id"] == "stats-fr-negation")
        result = assess_task(case["task"], self.tools)
        self.assertEqual(grade_assessment(case, result, self.tools), [])
        result["reasons"] = []
        self.assertTrue(grade_assessment(case, result, self.tools))

    def test_malformed_status_and_intent_fail_as_verdicts_instead_of_crashing(self):
        for field, value in (("intent", []), ("status", [])):
            result = copy.deepcopy(self.assessment)
            result[field] = value
            with self.subTest(field=field):
                self.assertTrue(grade_assessment(self.case, result, self.tools))
        case = next(case for case in self.corpus["cases"] if case["id"] == "stats-fr-negation")
        result = assess_task(case["task"], self.tools)
        result["intent"] = "invented_intent"
        self.assertTrue(grade_assessment(case, result, self.tools))

    def test_percentile_wording_preserves_negation_quotes_and_multiple_workflows(self):
        positive = assess_task("Report the 90th percentile of values 1, 2, 3, 4, 5.", self.tools)
        self.assertEqual(positive["intent"], "statistics")
        for task in (
            "Ne donne pas le 90e percentile des valeurs 1, 2, 3.",
            '"Report the 90th percentile of values 1, 2, 3."',
            "Donne le 90e percentile des valeurs 1, 2, 3 puis corrige le code.",
        ):
            with self.subTest(task=task):
                result = assess_task(task, self.tools)
                self.assertEqual(result["status"], "abstained")
                self.assertEqual(result["candidate_tools"], [])

    def test_reporting_percentiles_as_an_explanation_subject_is_not_a_calculation(self):
        for task in (
            "Explain why we report the 90th percentile of durations.",
            "Explique pourquoi on donne le 90e percentile des durées.",
        ):
            with self.subTest(task=task):
                result = assess_task(task, self.tools)
                self.assertNotEqual(result["intent"], "statistics")
                self.assertNotIn("compute_statistics", [tool["name"] for tool in result["candidate_tools"]])

    def test_future_codex_criteria_are_retained_without_becoming_offline_successes(self):
        original = evaluate(self.corpus)
        corpus = copy.deepcopy(self.corpus)
        corpus["cases"][0]["codex"]["checks"].append("A future real Codex trace must be reviewed.")
        changed = evaluate(corpus)
        self.assertEqual(changed["summary"], original["summary"])
        self.assertEqual(changed["model_selection"], original["model_selection"])
        self.assertNotEqual(changed["provenance"]["corpus_sha256"],
                            original["provenance"]["corpus_sha256"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EvaluationTests)
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
