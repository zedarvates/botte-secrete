"""Isolated coverage for context selection boundaries and reuse limits."""

import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.context_budget import Item, knapsack, select_skills


class ContextEffectsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def skill(self, folder, name, extra=""):
        path = self.root / folder / "SKILL.md"
        path.parent.mkdir()
        path.write_text(f"---\nname: {name}\ndescription: needle fixture\n---\nneedle {extra}\n", encoding="utf-8")
        return path

    def test_requested_pool_is_not_silently_limited_to_five(self):
        for n in range(8):
            self.skill(f"skill-{n}", f"skill-{n}")
        result = select_skills("needle", budget=4000, pool=8, roots=[self.root])
        self.assertEqual(len(result["chosen"]), 8)
        self.assertEqual(len(select_skills("needle", budget=4000, pool=6, roots=[self.root])["chosen"]), 6)

    def test_unselected_namesake_keeps_its_path_in_dropped(self):
        small = self.skill("small", "same-name")
        large = self.skill("large", "same-name", "extra " * 500)
        result = select_skills("needle", budget=100, roots=[self.root])
        self.assertEqual([row["ref"] for row in result["chosen"]], [str(small)])
        self.assertEqual([row["ref"] for row in result["dropped"]], [str(large)])

    def test_invalid_budget_unit_and_item_values_are_rejected(self):
        item = Item("a", "doc", 10, 1.0)
        cases = [([item], -1, 20), ([item], True, 20), ([item], 100, 0),
                 ([item], 100, -1), ([item], 100, 1.5),
                 ([Item("a", "doc", -1, 1)], 100, 20),
                 ([Item("a", "doc", 1.5, 1)], 100, 20),
                 ([Item("a", "doc", 1, float("nan"))], 100, 20),
                 ([Item("a", "doc", 1, float("inf"))], 100, 20)]
        for items, budget, unit in cases:
            with self.subTest(budget=budget, unit=unit, items=items), self.assertRaises(ValueError):
                knapsack(items, budget, unit=unit)

    def test_invalid_selection_options_do_not_load_catalog(self):
        with patch("skills.skill_finder.load_catalog", side_effect=AssertionError("must not read")):
            for options in ({"budget": -1}, {"pool": -1}, {"pool": True}):
                self.assertIn("error", select_skills("needle", **options))

    def test_quantization_can_omit_an_item_that_fits_original_budget(self):
        items = [Item("a", "doc", 11, 2)]
        self.assertEqual(knapsack(items, 11, unit=20)[0], [])
        self.assertEqual(knapsack(items, 11, unit=1)[0], [0])

    def test_solver_matches_exhaustive_search_in_quantized_space(self):
        items = [Item(str(n), "doc", cost, value) for n, (cost, value) in
                 enumerate([(0, 1), (11, 3), (20, 4), (21, 5)])]
        for unit, budget in itertools.product([1, 10, 20], [0, 19, 40, 60, 100]):
            chosen, tokens, value = knapsack(items, budget, unit=unit)
            expected = max(sum(it.relevance for it, take in zip(items, mask) if take)
                           for mask in itertools.product([False, True], repeat=len(items))
                           if sum(max(1, (it.tokens + unit - 1) // unit) for it, take in zip(items, mask) if take) <= budget // unit)
            self.assertEqual(value, expected)
            self.assertLessEqual(tokens, budget)
            self.assertEqual(len(chosen), len(set(chosen)))

    def test_selection_reads_fixtures_without_changing_them(self):
        path = self.skill("candidate", "candidate", "évidence")
        before = path.read_bytes()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            result = select_skills("needle", budget=100, roots=[self.root])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(result["cloud_tokens"], 0)
        self.assertEqual(json.loads(json.dumps(result))["chosen"][0]["ref"], str(path))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContextEffectsTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
