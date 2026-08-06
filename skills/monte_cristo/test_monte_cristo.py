"""Tests for the Monte Cristo prompt, contract, CLI, and loader integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from skills.capabilities import curate, load as load_capabilities
from skills.loader import (
    list_agents,
    load_agent,
    load_agents_batch,
    suggest_agents,
)
from skills.monte_cristo.cli import main
from skills.monte_cristo.contract import new_report, validate_report
from skills.monte_cristo.evaluation import (
    automatic_activation_allowed,
    benchmark,
    load_cases,
)
from skills.monte_cristo.routing import TriggerContext, evaluate_trigger


ROOT = Path(__file__).resolve().parents[2]
AGENT_FILE = ROOT / "agents" / "monte-cristo.md"
SCHEMA_FILE = Path(__file__).with_name("report.schema.json")


class MonteCristoContractTests(unittest.TestCase):
    def test_new_report_is_valid(self) -> None:
        self.assertEqual(validate_report(new_report("Reassess the platform")), [])

    def test_mutating_move_requires_approval(self) -> None:
        report = new_report("Replace the platform")
        report["moves"] = [{
            "id": "MC-1",
            "priority": "P1",
            "decision": "REPLACE",
            "target": "legacy platform",
            "rationale": "Recurring cost exceeds verified value.",
            "evidence": [{
                "kind": "OBSERVED",
                "ref": "costs.csv:12",
                "note": "Maintenance cost increased for three periods.",
            }],
            "blast_radius": "All clients require a compatibility bridge.",
            "validation": "Run a bounded compatibility prototype.",
            "approval_required": False,
        }]
        report["verdict"] = "REPLACE"
        errors = validate_report(report)
        self.assertTrue(any("must be true for REPLACE" in error for error in errors))

    def test_high_confidence_requires_observed_evidence(self) -> None:
        report = new_report("Research direction")
        report["confidence"] = 80
        errors = validate_report(report)
        self.assertTrue(any("maximum is 40" in error for error in errors))

    def test_p0_requires_observed_evidence(self) -> None:
        report = new_report("Security boundary")
        report["moves"] = [{
            "id": "MC-1",
            "priority": "P0",
            "decision": "INVESTIGATE",
            "target": "trust boundary",
            "rationale": "A secondary report alleges exposure.",
            "evidence": [{
                "kind": "INFERRED",
                "ref": "review.md:8",
                "note": "The primary trace is unavailable.",
            }],
            "blast_radius": "Unknown until the trace is recovered.",
            "validation": "Recover and reproduce the primary trace.",
            "approval_required": False,
        }]
        errors = validate_report(report)
        self.assertTrue(any("P0 requires OBSERVED" in error for error in errors))

    def test_schema_file_is_valid_json(self) -> None:
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        self.assertEqual(schema["title"], "Monte Cristo Strategic Report v1")

    def test_cli_validates_utf8_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "rapport.json"
            report_path.write_text(
                json.dumps(new_report("Décision stratégique"), ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(main(["validate", str(report_path)]), 0)


class MonteCristoAgentTests(unittest.TestCase):
    def test_agent_definition_is_triggerable_and_read_only(self) -> None:
        content = AGENT_FILE.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\nname: monte-cristo\n"))
        self.assertIn("Use this agent when", content)
        self.assertIn("## When to invoke", content)
        self.assertIn('tools: ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]', content)
        self.assertNotIn('tools: ["Read", "Write"', content)
        self.assertIn("You are the Count of Monte Cristo", content)

    def test_native_loader_exposes_agent(self) -> None:
        self.assertIn("monte_cristo", list_agents())
        context = load_agent("monte_cristo", project_root="C:/project")
        self.assertIn("above the blue and red teams", context)
        self.assertIn("Project root: `C:/project`", context)

    def test_batch_loader_withholds_terminal_toolset(self) -> None:
        task = load_agents_batch([
            ("monte_cristo", "Reassess the system", None),
        ])[0]
        self.assertEqual(task["toolsets"], ["file", "web", "skills"])


class MonteCristoRoutingTests(unittest.TestCase):
    def test_explicit_request_triggers(self) -> None:
        decision = evaluate_trigger(
            "Demande au comte de Monte-Cristo de remettre le projet en question."
        )
        self.assertTrue(decision.invoke)
        self.assertIn("explicit_request", decision.signals)

    def test_implicit_blue_red_frame_triggers(self) -> None:
        decision = evaluate_trigger(
            "L'équipe bleue et l'équipe rouge restent dans le même cadre."
        )
        self.assertTrue(decision.invoke)
        self.assertIn("blue_red_stalemate", decision.signals)
        self.assertIn("inherited_frame", decision.signals)

    def test_documented_compact_blue_red_phrase_triggers(self) -> None:
        decision = evaluate_trigger("Blue and red teams share the same frame.")
        self.assertTrue(decision.invoke)
        self.assertIn("blue_red_stalemate", decision.signals)

    def test_routine_review_does_not_trigger(self) -> None:
        decision = evaluate_trigger(
            "Monte-Cristo, review this small function for a typo."
        )
        self.assertFalse(decision.invoke)
        self.assertIn("routine_scope", decision.signals)

    def test_context_can_trigger_without_magic_words(self) -> None:
        decision = evaluate_trigger(
            "Reassess the direction.",
            TriggerContext(blue_red_stalled=True, inherited_frame=True),
        )
        self.assertTrue(decision.invoke)

    def test_loader_suggests_without_execution(self) -> None:
        suggestions = suggest_agents(
            "Should we replace this inherited architecture before a costly rewrite?"
        )
        self.assertEqual(suggestions[0]["name"], "monte_cristo")
        self.assertEqual(suggestions[0]["gate"]["cases"], len(load_cases()))
        self.assertEqual(suggestions[0]["gate"]["precision"], 1.0)

    def test_capability_registry_discovers_decide_layer(self) -> None:
        capabilities = load_capabilities()
        monte = next(c for c in capabilities if c.name == "monte_cristo")
        self.assertEqual(monte.layer, "DECIDE")
        self.assertFalse(monte.local_capable)
        ranked = curate("strategic outsider inherited architecture assumptions")
        self.assertIn("monte_cristo", [item["name"] for item in ranked[:3]])


class MonteCristoEvaluationTests(unittest.TestCase):
    def test_tracked_corpus_is_bilingual_balanced_and_unique(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 40)
        self.assertEqual({case.language for case in cases}, {"fr", "en"})
        self.assertGreaterEqual(sum(case.expected for case in cases), 16)
        self.assertGreaterEqual(sum(not case.expected for case in cases), 16)
        self.assertEqual(len({case.id for case in cases}), len(cases))

    def test_trigger_corpus_passes_fail_closed_gate(self) -> None:
        result = benchmark(load_cases())
        self.assertTrue(result.meets_activation_gate(), result.to_dict())
        self.assertTrue(automatic_activation_allowed(result))
        self.assertEqual(result.false_positives, 0)
        self.assertEqual(result.routine_false_positives, 0)

    def test_missing_or_false_positive_result_blocks_activation(self) -> None:
        result = benchmark(load_cases())
        unsafe = replace(
            result,
            false_positives=1,
            routine_false_positives=1,
            false_positive_ids=("synthetic-fp",),
        )
        self.assertFalse(automatic_activation_allowed(None))
        self.assertFalse(automatic_activation_allowed(unsafe))

    def test_literary_reference_does_not_trigger_agent(self) -> None:
        decision = evaluate_trigger("Résume le roman Le Comte de Monte-Cristo.")
        self.assertFalse(decision.invoke)
        self.assertIn("non_agent_reference", decision.signals)


if __name__ == "__main__":
    unittest.main()
