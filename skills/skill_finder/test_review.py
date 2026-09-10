"""Selection protocol regressions; model replies are injected, not evaluated."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skills.skill_finder import finder


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        for vendor, mode in (("a", "private notes"), ("b", "shared observations")):
            path = self.root / vendor / "memory" / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "---\nname: memory\ndescription: Inspect memory records.\n---\n"
                f"Read {mode}. Do not delete records.\n"
                "Prerequisite: the caller supplies the authorized project.\n",
                encoding="utf-8")
            self.paths.append(str(path))
        self.catalog = finder.load_catalog([self.root])
        self.matches = finder.rank("inspect memory", self.catalog)
        self.backend = patch("skills.llm_backends.registry.best_chat_backend", return_value=True)
        self.backend.start()
        self.addCleanup(self.backend.stop)
        client = patch("skills.llm_backends.client.LocalLLMClient")
        self.client = client.start()
        self.addCleanup(client.stop)

    def find(self, reply):
        self.client.return_value.chat.return_value = SimpleNamespace(text=reply)
        return finder.find("inspect memory", roots=[self.root], use_local=True)

    def test_same_name_selection_filters_by_path(self):
        result = self.find("2")
        self.assertEqual([m["path"] for m in result["matches"]], self.paths[1:])
        self.assertEqual(result["local_review"]["status"], "selected")

    def test_model_order_and_duplicate_numbers(self):
        result = self.find("2,2,1")
        self.assertEqual([m["path"] for m in result["matches"]], self.paths[::-1])

    def test_explicit_abstention_is_not_lexical_fallback(self):
        result = self.find("0")
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["local_review"]["status"], "abstained")

    def test_invalid_response_retains_advisory_shortlist(self):
        for reply in ("", "Choose 2", "2,99", "0,1", "-1", "2.0", "9" * 1100, None):
            with self.subTest(reply=reply):
                result = self.find(reply)
                self.assertEqual([m["path"] for m in result["matches"]], self.paths)
                self.assertEqual(result["tier"], "free-lexical")
                self.assertEqual(result["local_review"]["reason"], "invalid_response")

    def test_full_bodies_and_exact_bytes_are_bound(self):
        result = self.find("2")
        prompt = self.client.return_value.chat.call_args.args[0]
        payload = json.loads(prompt.split("\n\n", 1)[1].rsplit("\n\nAnswer:", 1)[0])
        self.assertEqual(len(payload["candidates"]), 2)
        for document, path in zip(payload["candidates"], self.paths):
            raw = Path(path).read_bytes()
            self.assertEqual(document["instructions"], raw.decode("utf-8"))
            self.assertEqual(result["local_review"]["instruction_sha256"][path],
                             hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["local_review"]["authority"], "advisory")
        self.assertFalse(result["local_review"]["referenced_resources_read"])

    def test_over_budget_never_sends_a_truncated_prompt(self):
        with patch.object(finder, "MAX_REVIEW_BYTES", 20):
            result = self.find("2")
        self.assertEqual(result["local_review"]["reason"], "instruction_budget_exceeded")
        self.client.assert_not_called()

    def test_missing_or_invalid_instruction_prevents_call(self):
        for mode in ("missing", "invalid_utf8", "empty"):
            with self.subTest(mode=mode):
                path = Path(self.paths[1])
                if mode == "missing":
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(b"\xff" if mode == "invalid_utf8" else b"\n")
                with patch.object(finder, "load_catalog", return_value=self.catalog):
                    result = self.find("2")
                self.assertEqual(result["local_review"]["status"], "unavailable")
                self.client.assert_not_called()

    def test_no_backend_preserves_lexical_search(self):
        with patch("skills.llm_backends.registry.best_chat_backend", return_value=None):
            result = self.find("2")
        self.assertEqual(result["local_review"]["reason"], "no_local_backend")
        self.assertEqual([m["path"] for m in result["matches"]], self.paths)
        self.client.assert_not_called()

    def test_model_error_is_unavailable_not_abstained(self):
        from skills.llm_backends.client import LocalLLMError
        self.client.return_value.chat.side_effect = LocalLLMError("fixture failure")
        result = self.find("0")
        self.assertEqual(result["local_review"]["reason"], "local_model_error")
        self.assertEqual(len(result["matches"]), 2)

    def test_legacy_helper_and_path_option(self):
        self.client.return_value.chat.return_value = SimpleNamespace(text="2,1")
        self.assertEqual(finder.local_rerank("inspect memory", self.matches), ["memory", "memory"])
        self.assertEqual(finder.local_rerank("inspect memory", self.matches, include_paths=True),
                         self.paths[::-1])

    def test_lexical_mode_never_calls_model(self):
        result = finder.find("inspect memory", roots=[self.root])
        self.assertNotIn("local_review", result)
        self.client.assert_not_called()

    def test_relative_external_root_preserves_identity(self):
        previous_directory = Path.cwd()
        try:
            os.chdir(self.root)
            self.client.return_value.chat.return_value = SimpleNamespace(text="2")
            result = finder.find("inspect memory", roots=[Path(".")], use_local=True)
        finally:
            os.chdir(previous_directory)
        self.assertEqual([m["path"] for m in result["matches"]], self.paths[1:])
        self.assertEqual(result["local_review"]["status"], "selected")

    def test_relative_path_cannot_bind_unrelated_repo_instructions(self):
        path = self.root / "skills" / "skill_finder" / "SKILL.md"
        path.parent.mkdir(parents=True)
        body = "---\nname: private_memory\ndescription: Inspect private records.\n---\nPrivate fixture only."
        path.write_text(body, encoding="utf-8")
        previous_directory = Path.cwd()
        try:
            os.chdir(self.root)
            self.client.return_value.chat.return_value = SimpleNamespace(text="1")
            result = finder.find("private records", roots=[Path("skills")], use_local=True)
        finally:
            os.chdir(previous_directory)
        self.assertEqual([m["path"] for m in result["matches"]], [str(path)])
        self.assertEqual(result["local_review"]["instruction_sha256"],
                         {str(path): hashlib.sha256(body.encode("utf-8")).hexdigest()})
        prompt = self.client.return_value.chat.call_args.args[0]
        self.assertIn(json.dumps(body), prompt)

    def test_empty_shortlist_is_not_model_abstention(self):
        result = finder.find("", roots=[self.root], use_local=True)
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["local_review"]["reason"], "empty_shortlist")
        self.assertEqual(result["local_review"]["status"], "unavailable")
        self.client.assert_not_called()


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    failed = len(result.errors) + len(result.failures)
    passed = max(0, result.testsRun - failed - len(result.skipped))
    print(f"RESULT: {passed} passed, {failed} failed, {len(result.skipped)} skipped")
    raise SystemExit(0 if result.wasSuccessful() else 1)
