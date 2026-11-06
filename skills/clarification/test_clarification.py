"""Clarification must preserve unanswered blockers and existing context."""

from __future__ import annotations

import unittest

from skills.clarification import (
    ClarificationRequest, Question, QuestionPriority, dartagnan_clarify,
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


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ClarificationTests))
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
