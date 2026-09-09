"""Preserve context text and observe prefix-state effects in isolated fixtures."""

import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.prefix_pruner import pruner
from skills.prefix_tree import cli as prefix_cli


class PrefixEffectsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(pruner, "PREFIX_STORE", self.root / "usage.json").start()
        patch.object(prefix_cli, "TREE_STORE", self.root / "prefixes.json").start()

    def test_kept_context_preserves_order_gaps_and_whitespace(self):
        content = "Important preamble.\n\n# Tools\nalpha\n# Other\nkeep this\n# Context\nbeta\n"
        self.assertEqual(pruner.prune_content(content), content)

    def test_removal_changes_only_selected_span_and_logs_to_stderr(self):
        content = "preamble\n# Tools\nold\n# Other\nuntouched\n# Context\nnew\n"
        tree = pruner.PrefixTree()
        section = pruner.split_sections(content)[0]
        sid = hashlib.sha256(section["content"].encode()).hexdigest()[:12]
        tree.register_section(sid, "tools", section["content"], 3)
        tree.record_use(sid)
        for _ in range(4):
            tree.record_skip(sid)
        with contextlib.redirect_stdout(io.StringIO()) as stdout, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = pruner.prune_content(content, tree, "aggressive")
        self.assertEqual(result, content[:section["start"]] + content[section["end"]:])
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Pruned", stderr.getvalue())

    def test_nested_spans_are_not_duplicated(self):
        content = "<context>\n# Memory\ninside\n</context>\n# Tools\noutside\n"
        spans = pruner.split_sections(content)
        self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(spans, spans[1:])))
        self.assertEqual(pruner.prune_content(content), content)

    def test_single_section_is_unchanged_without_store_write(self):
        content = "# Context\nunchanged\n"
        self.assertEqual(pruner.prune_content(content), content)
        self.assertFalse(pruner.PREFIX_STORE.exists())

    def test_shortened_or_replaced_prefix_returns_full_replacement(self):
        tree = prefix_cli.PrefixTrie()
        tree.register("fixture", "keep this instruction")
        for content in ("keep", "", "new instruction"):
            with self.subTest(content=content):
                self.assertEqual(tree.diff("fixture", content), content)

    def test_append_delta_preserves_whitespace_and_does_not_update_baseline(self):
        tree = prefix_cli.PrefixTrie()
        tree.register("fixture", "base")
        for delta in (" \n", "\n  suite é  \n"):
            with self.subTest(delta=delta):
                self.assertEqual(tree.diff("fixture", "base" + delta),
                                 f"[diff:+{len(delta)}c] {delta}")
        self.assertEqual(tree.diff("fixture", "base"), "[no change]")
        self.assertEqual(prefix_cli.PrefixTrie().get_prefix("fixture"), "base")

    def test_prefix_read_operations_leave_plaintext_store_unchanged(self):
        tree = prefix_cli.PrefixTrie()
        tree.register("fixture", "préfixe confidentiel fictif")
        before = prefix_cli.TREE_STORE.read_bytes()
        self.assertIn("fixture", tree.stats()["agents_list"])
        self.assertEqual(tree.common_prefix(["fixture"]), tree.get_prefix("fixture"))
        self.assertEqual(prefix_cli.TREE_STORE.read_bytes(), before)


def main():
    result = unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PrefixEffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
