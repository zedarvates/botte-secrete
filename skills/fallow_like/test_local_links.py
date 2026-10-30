"""Behavioral tests for supplied-data local Markdown target checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skills.fallow_like.local_links import check_local_links, extract_markdown_links


def check(text, paths=(), *, path="docs/start.md", complete=True, **kwargs):
    return check_local_links([{"path": path, "text": text}], list(paths),
                             inventory_complete=complete, **kwargs)


class LocalLinksTests(unittest.TestCase):
    def test_present_missing_and_relative_directories(self):
        report = check("[ok](../README.md) [directory](assets/) ![no](assets/no.png)",
                       ["README.md", "docs/assets/present.png"])
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["counts"]["present"], 2)
        self.assertEqual(report["counts"]["missing"], 1)
        self.assertEqual(report["findings"][0]["resolved_path"], "docs/assets/no.png")
        self.assertEqual(report["findings"][0]["line"], 1)

    def test_incomplete_inventory_never_establishes_missing(self):
        report = check("[no](missing.md)", complete=False)
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["counts"]["unresolved"], 1)
        self.assertEqual(report["status"], "partial")
        self.assertIn("inventory_incomplete", report["coverage"]["reasons"])
        self.assertEqual(check("[self](start.md)", complete=False)["status"], "partial")

    def test_supplied_source_is_known_even_without_inventory_entry(self):
        report = check("[self](start.md) [root](../)")
        self.assertEqual(report["counts"]["present"], 2)

    def test_path_case_is_preserved(self):
        report = check("[x](Photo.PNG) [y](photo.png)", ["docs/Photo.PNG"])
        self.assertEqual(report["counts"]["present"], 1)
        self.assertEqual(report["counts"]["missing"], 1)

    def test_percent_decoding_and_containment(self):
        report = check("[ok](a%20b.md#part) [escape](%2e%2e/%2e%2e/no.md) [root](%2fetc/passwd)",
                       ["docs/a b.md"])
        self.assertEqual(report["counts"]["present"], 1)
        self.assertEqual(report["counts"]["outside_root"], 2)
        self.assertEqual(report["status"], "partial")

    def test_external_urls_and_anchors_are_counted_but_not_checked(self):
        report = check("[x](https://example.invalid/a) [m](mailto:a@b) [n](//example.invalid/a) [a](#part) [q](?view=1)")
        self.assertEqual(report["counts"]["external"], 3)
        self.assertEqual(report["counts"]["anchor_only"], 2)
        self.assertEqual(report["counts"]["links_examined"], 5)
        self.assertEqual(report["counts"]["missing"], 0)

    def test_balanced_escaped_parentheses_titles_and_angle_paths(self):
        report = check(r'''[a](a(b).md "title") [b](escaped\(x\).md) [c](<file name.md> 'title')''',
                       ["docs/a(b).md", "docs/escaped(x).md", "docs/file name.md"])
        self.assertEqual(report["counts"]["present"], 3)
        self.assertEqual(report["counts"]["unsupported"], 0)

    def test_images_nested_inside_link_labels(self):
        report = check("[![image](pic.png)](destination.md)", ["docs/destination.md"])
        self.assertEqual(report["counts"]["present"], 1)
        self.assertEqual(report["counts"]["missing"], 1)

    def test_escaped_label_and_entity_destination(self):
        report = check(r'\[literal](ignored.md) [real](a&amp;b.md)', ["docs/a&b.md"])
        self.assertEqual(report["counts"]["links_examined"], 1)
        self.assertEqual(report["counts"]["present"], 1)

    def test_code_comments_and_indented_blocks_are_excluded(self):
        text = '''`[inline](no)` and ``[also](no)``
<!-- [comment](no)
[comment2](no) --> [real](ok.md)
~~~~ language
[fenced](no)
```
~~~~
    [indented](no)
\t[indented2](no)
````md
<!-- [inside](no)
```
[still](no)
````
[visible](ok.md)
'''
        report = check(text, ["docs/ok.md"])
        self.assertEqual(report["counts"]["links_examined"], 2)
        self.assertEqual(report["counts"]["present"], 2)

    def test_review_comment_markers_in_code_do_not_hide_real_links(self):
        for text in ('`<!--` [x](missing.md)', '```html\n<!--\n```\n[x](missing.md)'):
            with self.subTest(text=text):
                report = check(text)
                self.assertEqual(report["counts"]["missing"], 1)

    def test_review_multiline_code_is_not_reported_as_broken_link(self):
        report = check('`line one\n[x](missing.md)\nline three`')
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["status"], "partial")

    def test_review_container_and_nested_links_are_partial(self):
        examples = ('> ```\n> [x](missing.md)\n> ```', '- item\n    [x](missing.md)',
                    '[outer [inner](inner.md)](outer.md)', '<video src="missing.mp4"></video>')
        for text in examples:
            with self.subTest(text=text):
                report = check(text)
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["counts"]["missing"], 0)

    def test_raw_html_blocks_do_not_turn_literal_markdown_into_missing(self):
        report = check('<div>\n[x](literal-not-a-link.md)\n</div>\n\n[x](actual-missing.md)')
        self.assertEqual(report["counts"]["missing"], 1)
        self.assertEqual(report["findings"][-1]["target"], "actual-missing.md")
        self.assertEqual(report["status"], "partial")

    def test_inline_html_attributes_are_not_markdown_links(self):
        report = check('prefix <a href="[x](literal.md)">x</a>')
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["status"], "partial")

    def test_indirect_nested_link_is_not_declared_missing(self):
        report = check('[outer [literal [inner](inner.md)]](outer.md)')
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["status"], "partial")

    def test_review_inline_generic_tag_and_raw_blankline_are_partial(self):
        for text in ('A <span title="[x](missing.md)">hello</span>',
                     '<script>\n\n[x](missing.md)\n</script>',
                     'A <script>\n[x](missing.md)\n</script>'):
            with self.subTest(text=text):
                report = check(text)
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["counts"]["missing"], 0)

    def test_angle_destination_without_extension_is_supported(self):
        self.assertEqual(check('[x](<target>)', ['docs/target'])["counts"]["present"], 1)

    def test_unterminated_inline_html_does_not_parse_attributes_as_links(self):
        for text in ('prefix <a\n title="[x](missing.md)"\n>x</a>',
                     'prefix <a title="greater >\n[x](missing.md)\n">x</a>'):
            with self.subTest(text=text):
                report = check(text)
                self.assertEqual(report["counts"]["missing"], 0)
                self.assertEqual(report["status"], "partial")
                self.assertIn("multiline_html_tag_not_checked",
                              [item["reason"] for item in report["findings"]])

    def test_many_inline_links_use_a_bounded_linear_pass(self):
        report = check('[x](a.md) ' * 10000, ['docs/a.md'], max_links=10000)
        self.assertEqual(report["counts"]["present"], 10000)
        self.assertEqual(report["status"], "complete")

    def test_reference_definitions_explicit_collapsed_shortcut(self):
        text = '''[explicit][Guide] [guide][] [guide] ![picture][im]
[guide]: ../Guide.md "help"
[im]: <a b.png>
'''
        report = check(text, ["Guide.md", "docs/a b.png"])
        self.assertEqual(report["counts"]["present"], 4)
        self.assertEqual(report["counts"]["missing"], 0)

    def test_reference_definitions_first_wins_and_casefold(self):
        report = check("[x][A]\n[A]: yes.md\n[a]: no.md", ["docs/yes.md"])
        self.assertEqual(report["counts"]["present"], 1)

    def test_undefined_references_are_literal_markdown(self):
        self.assertEqual(check("[literal][undefined] [checklist] [ ] done")["counts"]["links_examined"], 0)

    def test_recognized_unsupported_syntax_is_partial(self):
        for text in ('<a href="x.md">x</a>', '[x](\nmissing.md)', '[x]\n(missing.md)', '[ref]:\n  target.md', '[x](unclosed'):
            with self.subTest(text=text):
                report = check(text)
                self.assertEqual(report["status"], "partial")
                self.assertGreater(report["counts"]["unsupported"], 0)

    def test_windows_and_absolute_paths_do_not_become_repo_paths(self):
        report = check(r'[x](C:/windows/x) [y](C:\windows\x) [z](/etc/x)')
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["counts"]["unsupported"], 2)
        self.assertEqual(report["counts"]["outside_root"], 1)

    def test_links_limit_includes_external_and_anchors(self):
        report = check("[x](#part) [e](https://example.invalid) [y](missing.md)", max_links=2)
        self.assertEqual(report["counts"]["links_examined"], 2)
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertIn("max_links", report["coverage"]["reasons"])

    def test_budget_boundary_and_unparsed_later_documents(self):
        self.assertEqual(check("[x](missing.md)", max_links=1)["status"], "complete")
        report = check_local_links([{"path": "a.md", "text": "[x](#part)"},
                                    {"path": "b.md", "text": "[missing](no)"}], [],
                                   inventory_complete=True, max_links=1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["counts"]["links_examined"], 1)

    def test_findings_are_bounded_and_have_omitted_count(self):
        report = check(" ".join(f"[x](missing{i}.md)" for i in range(60)))
        self.assertEqual(report["counts"]["missing"], 60)
        self.assertEqual(len(report["findings"]), 50)
        self.assertEqual(report["findings_omitted"], 10)
        self.assertTrue(report["report_truncated"])
        self.assertFalse(report["coverage"]["partial"])
        self.assertEqual(report["status"], "partial")

    def test_unsupported_details_also_bounded(self):
        report = check('\n'.join('prefix <img src="not-checked.png">' for _ in range(70)))
        self.assertEqual(report["counts"]["unsupported"], 70)
        self.assertEqual(report["findings_omitted"], 20)

    def test_input_order_does_not_change_output(self):
        docs = [{"path": "b.md", "text": "[b](missing-b)"}, {"path": "a.md", "text": "[a](missing-a)"}]
        a = check_local_links(docs, ["z", "a"], inventory_complete=True)
        b = check_local_links(list(reversed(docs)), ["a", "z"], inventory_complete=True)
        self.assertEqual(a, b)

    def test_no_filesystem_or_network_access(self):
        with patch("builtins.open", side_effect=AssertionError("unexpected filesystem")):
            report = check("[x](present.md)", ["docs/present.md"])
        self.assertEqual(report["counts"]["present"], 1)
        self.assertEqual(report["boundaries"], {"filesystem": False, "network": False, "model_calls": 0})

    def test_invalid_paths_and_types_are_rejected(self):
        invalid_paths = ["/a.md", "../a.md", "a/../b.md", "a//b.md", "./a.md", "C:/a.md", "a\\b.md", "a\x00.md", "a\n.md", "", "a" * 4097, "a/", "md"]
        for path in invalid_paths:
            with self.subTest(path=repr(path)):
                with self.assertRaises(ValueError):
                    check_local_links([{"path": path, "text": ""}], [])
        for value in (True, 0, -1, 50001, 1.5, "1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    check("", max_links=value)
        for complete in (None, 1, "true"):
            with self.assertRaises(ValueError):
                check_local_links([{"path": "a.md", "text": ""}], [], inventory_complete=complete)

    def test_invalid_collections_and_unknown_document_fields(self):
        for docs in (None, [], {}, [{"path": "a.md"}], [{"path": "a.md", "text": "", "extra": 1}], [{"path": "a.md", "text": 3}], [{"path": "a.md", "text": ""}] * 201):
            with self.subTest(docs=str(docs)[:70]):
                with self.assertRaises(ValueError):
                    check_local_links(docs, [])
        for inventory in (None, {}, ["a", "a"], ["a"] * 50001, ["../a"]):
            with self.assertRaises(ValueError):
                check_local_links([{"path": "a.md", "text": ""}], inventory)
        with self.assertRaises(ValueError):
            check_local_links([{"path": "a.md", "text": ""}] * 2, [])

    def test_byte_and_unicode_limits(self):
        with self.assertRaises(ValueError):
            check("a" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            check("\ud800")
        docs = [{"path": f"{i}.md", "text": "a" * (1024 * 1024)} for i in range(9)]
        with self.assertRaises(ValueError):
            check_local_links(docs, [])
        with self.assertRaises(ValueError):
            check_local_links([{"path": "a.md", "text": ""}], [f"{i}" + "a" * 4090 for i in range(2100)])

    def test_overlong_target_is_not_echoed(self):
        report = check("[x](" + "a" * 4097 + ")")
        self.assertEqual(report["counts"]["unsupported"], 1)
        self.assertIsNone(report["findings"][0]["target"])

    def test_invalid_percent_utf8_and_encoded_backslash(self):
        report = check("[x](%ff.md) [y](%5cetc%5cx)")
        self.assertEqual(report["counts"]["unsupported"], 1)
        self.assertEqual(report["counts"]["outside_root"], 1)
        self.assertEqual(report["counts"]["missing"], 0)

    def test_deep_brackets_are_partial(self):
        report = check("[" * 40 + "x" + "]" * 40 + "(x.md)")
        self.assertEqual(report["status"], "partial")
        self.assertIn("unsupported_markdown", report["coverage"]["reasons"])


class LegacyDocsScriptTests(unittest.TestCase):
    def test_legacy_script_uses_shared_extractor(self):
        script = Path(__file__).resolve().parents[2] / "scripts/check_docs_links.py"
        spec = importlib.util.spec_from_file_location("local_links_legacy_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "README.md"
            (root / "a(b).md").write_text("", encoding="utf-8")
            source.write_text('`[ignored](no)` [yes](a(b).md) [no](absent.md)', encoding="utf-8")
            self.assertEqual(module.broken_links(source), [(1, "absent.md")])
    def test_legacy_script_preserves_known_missing_with_partial_coverage(self):
        script = Path(__file__).resolve().parents[2] / "scripts/check_docs_links.py"
        spec = importlib.util.spec_from_file_location("local_links_legacy_mixed", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "README.md"
            source.write_text('prefix <span title="x">raw</span>\n\n[real](absent.md)', encoding="utf-8")
            self.assertEqual(module.broken_links(source), [(3, "absent.md")])
            self.assertEqual(module.main([str(source)]), 1)

    def test_legacy_script_partial_is_explicit(self):
        script = Path(__file__).resolve().parents[2] / "scripts/check_docs_links.py"
        spec = importlib.util.spec_from_file_location("local_links_legacy_partial", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "README.md"
            source.write_text('<video src="movie.mp4"></video>', encoding="utf-8")
            self.assertEqual(module.main([str(source)]), 0)
            self.assertEqual(module.main(["--strict-coverage", str(source)]), 3)
            source.write_text('a' * (1024 * 1024 + 1), encoding="utf-8")
            self.assertEqual(module.main([str(source)]), 0)
            self.assertEqual(module.main(["--strict-coverage", str(source)]), 3)



if __name__ == "__main__":
    unittest.main()
