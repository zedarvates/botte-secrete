"""Clarification must preserve unanswered blockers and existing context."""

from __future__ import annotations

import unittest
from pathlib import Path

from skills.clarification import (
    ClarificationRequest, Question, QuestionPriority, dartagnan_clarify,
    aramis_clarify, rochefort_clarify,
)


class ClarificationTests(unittest.TestCase):
    def request(self):
        return ClarificationRequest("agent", "prepare", [
            Question(1, "Format du rapport ?", default_answer="JSON"),
            Question(2, "Quelle cible ?", QuestionPriority.BLOCKER, "production"),
            Question(3, "Publier ?", QuestionPriority.LOW, "oui",
                     requires_explicit_answer=True),
            Question(4, "Une précision ?"),
        ])

    def test_defaults_do_not_resolve_blockers_or_authorizations(self):
        request = self.request()
        self.assertEqual(request.fill_defaults(), {1: "JSON"})
        self.assertEqual([q.number for q in request.blocking_questions()], [2, 3])

    def test_existing_answers_are_not_requested_or_defaulted_again(self):
        request = self.request()
        known = {1: "Markdown", 2: "isolated", 3: "Do not publish", 4: "none"}
        self.assertEqual(request.pending_questions(known), [])
        self.assertEqual(request.fill_defaults(known), {})
        self.assertEqual(request.blocking_questions(known), [])
        self.assertEqual(request.to_prompt(known), "")
        self.assertEqual(len(request.questions), 4)

    def test_partial_context_retains_only_unanswered_questions(self):
        request = self.request()
        self.assertEqual([q.number for q in request.pending_questions({2: "sandbox"})],
                         [1, 3, 4])
        self.assertEqual([q.number for q in request.blocking_questions({2: "sandbox"})],
                         [3])

    def test_silence_and_auto_do_not_answer_a_blocker(self):
        for value in ("", "  ", "auto", " AUTO ", None):
            with self.subTest(answer=value):
                request = self.request()
                self.assertEqual([q.number for q in request.blocking_questions({2: value})],
                                 [2, 3])
                self.assertNotIn(2, request.fill_defaults({2: value}))

    def test_prompt_does_not_offer_risky_defaults(self):
        prompt = self.request().to_prompt()
        self.assertNotIn("_production_", prompt)
        self.assertNotIn("_oui_", prompt)
        self.assertIn("_JSON_", prompt)
        self.assertIn("aucune autorisation", prompt)

    def test_empty_and_missing_defaults_are_not_fabricated(self):
        request = ClarificationRequest("agent", "prepare", [
            Question(1, "Unknown"), Question(2, "Empty", default_answer=" "),
        ])
        self.assertEqual(request.fill_defaults(), {})
        self.assertEqual(len(request.pending_questions()), 2)

    def test_fix_generator_keeps_scope_unresolved_until_answered(self):
        request = dartagnan_clarify(3)
        self.assertNotIn(1, request.fill_defaults())
        self.assertEqual([q.number for q in request.blocking_questions()], [1])
        self.assertEqual(request.blocking_questions({1: "Already authorized in task"}), [])

    def test_dynamic_usage_is_unknown_without_evidence(self):
        for request in (aramis_clarify("python"), rochefort_clarify("report")):
            with self.subTest(agent=request.agent_name):
                self.assertNotIn(2, request.fill_defaults())
                self.assertIn(2, [q.number for q in request.pending_questions()])
                self.assertNotIn(2, [q.number for q in request.pending_questions({2: "verified"})])

    def test_role_prompts_do_not_assume_no_dynamic_usage(self):
        root = Path(__file__).resolve().parents[2]
        for path in ("skills/mousquetaires/prompts/aramis.md", "skills/cardinal/prompts/rochefort.md"):
            with self.subTest(path=path):
                text = (root / path).read_text(encoding="utf-8")
                line = next(line for line in text.splitlines() if line.startswith("2. 🟠 Appels dynamiques")
                            or line.startswith("2. 🟡 Frameworks dynamiques"))
                self.assertIn("inconnu", line)
                self.assertNotIn("défaut: NON", line)


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ClarificationTests))
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
