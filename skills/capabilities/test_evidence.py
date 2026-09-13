"""Targeted evidence reads preserve run context and reject ambiguous inputs."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request

from skills.capabilities import evidence
from skills.capabilities.cli import main as cli
from skills.capabilities.effects import contract_template
from skills.capabilities.evidence import read_evidence, read_saved_evidence, select_evidence
from skills.capabilities.network_observations import network_attempt
from skills.capabilities.observations import ObservationSession, digest, observed_file_write, validate_report
from skills.capabilities.review import after, before


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.skill = self.root / "skills" / "worker"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("---\nname: worker\ndescription: fixture\n---\n", encoding="utf-8")
        self.contract = contract_template(self.skill, "zedarvates/botte-secrete:skills/worker")
        self.contract["analysis"]["summary"] = "Unrequested retained declaration prose."
        (self.skill / "effects.json").write_text(json.dumps(self.contract), encoding="utf-8")
        patcher = patch("skills.capabilities.registry.REPO_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.output = self.root / "café.txt"
        url = "http://127.0.0.1/fixture"
        with ObservationSession() as session, session.call(self.skill, "parent"):
            try:
                with session.call(self.skill, "write"), observed_file_write(self.output, "/expected_effects/0"):
                    self.output.write_text("partial café\n", encoding="utf-8")
                    raise OSError("fixture write raised after changing the file")
            except OSError:
                pass
            with session.call(self.skill, "submit"):
                with network_attempt("http", Request(url), "/expected_effects/0", method="POST") as attempt:
                    attempt.response(SimpleNamespace(getcode=lambda: 202, geturl=lambda: url))
                    attempt.read_complete()
        self.report = session.report
        self.report["process"] = {"status": "exited", "exit_code": 0}
        self.report["problems"] = ["Only the selected fixture sites were observed."]
        self.assertEqual(validate_report(self.report), [])
        self.path = self.root / ".botte" / "reports" / "fixture.json"
        self.path.parent.mkdir(parents=True)
        self.save(self.report)

    def save(self, document):
        self.path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def test_index_keeps_failures_limits_and_digest_without_full_records(self):
        view = select_evidence(self.report)
        self.assertEqual(view["selection_status"], "indexed")
        self.assertEqual(view["evidence_sha256"], digest(self.report))
        self.assertIsNone(view["matches_expected"])
        self.assertEqual(view["index"]["calls"], {"returned": ["c1", "c3"], "raised": ["c2"]})
        self.assertEqual(view["index"]["observations"], {"deviation": ["o1"]})
        self.assertEqual(view["index"]["network"], {"returned": ["n1"]})
        self.assertEqual(view["summary"]["next_action"], "inspect_partial_state_before_retry")
        for field in ("context", "process", "problems", "limitations"):
            self.assertEqual(view[field], self.report[field])
        self.assertNotIn("Unrequested retained", json.dumps(view))
        self.assertNotIn(str(self.output), json.dumps(view))

    def test_exact_selection_links_ancestors_and_cannot_mutate_retained_evidence(self):
        original = deepcopy(self.report)
        view = select_evidence(self.report, ["/observations/o1", "/network/n1", "/calls/c1", "/network/n1"])
        self.assertEqual(view["selected"], {"/observations/o1": self.report["observations"][0],
                                           "/network/n1": self.report["network"][0],
                                           "/calls/c1": self.report["calls"][0]})
        self.assertEqual(view["linked_calls"], {c["id"]: c for c in self.report["calls"][1:]})
        self.assertEqual(view["selected"]["/network/n1"]["remote_effects"], "unknown")
        self.assertEqual(view["task_outcome"], "unverified")
        view["selected"]["/observations/o1"]["after"]["size"] = 0
        view["linked_calls"]["c2"]["status"] = "returned"
        view["problems"].clear()
        self.assertEqual(self.report, original)

    def test_retained_declaration_is_read_without_reinspecting_current_sources(self):
        self.skill.joinpath("SKILL.md").unlink()
        self.skill.joinpath("effects.json").unlink()
        ref = self.report["calls"][0]["declaration_ref"]
        view = read_evidence(self.path, [f"/declarations/{ref}"])
        self.assertEqual(view["selected"], {f"/declarations/{ref}": self.contract})
        self.assertEqual(view["linked_calls"], {})

    def test_changed_run_or_evidence_returns_no_fragments_until_explicit_refresh(self):
        for field, value in (("run_id", "0" * 32), ("process", {"status": "timed_out", "exit_code": -1})):
            changed = deepcopy(self.report)
            changed[field] = value
            view = select_evidence(changed, ["/observations/o1"], expected_sha256=digest(self.report))
            self.assertEqual(view["selection_status"], "changed")
            self.assertFalse(view["matches_expected"])
            self.assertEqual(view["selected"], {})
            self.assertNotIn("linked_calls", view)
            self.assertNotIn("index", view)
            fresh = select_evidence(changed)
            self.assertEqual(select_evidence(changed, ["/observations/o1"],
                             expected_sha256=fresh["evidence_sha256"])["selection_status"], "selected")

    def test_json_formatting_is_ignored_but_reordered_report_results_do_not_mix_runs(self):
        self.path.write_text(json.dumps(self.report, indent=4, sort_keys=True), encoding="utf-8")
        self.assertTrue(read_evidence(self.path, expected_sha256=digest(self.report))["matches_expected"])
        other = deepcopy(self.report)
        other["run_id"] = "0" * 32
        document = {"results": [{"effects_observed": self.report}, {"effects_observed": other}]}
        self.save(document)
        initial = read_evidence(self.path, result_index=0)
        document["results"].reverse()
        self.save(document)
        self.assertEqual(read_evidence(self.path, ["/calls/c1"], result_index=0,
                         expected_sha256=initial["evidence_sha256"])["selection_status"], "changed")

    def test_missing_selection_is_all_or_nothing_and_ids_are_not_array_indexes(self):
        view = select_evidence(self.report, ["/observations/o1", "/network/n99", "/calls/0"])
        self.assertEqual(view["selection_status"], "not_found")
        self.assertEqual(view["missing_selectors"], ["/network/n99", "/calls/0"])
        self.assertEqual(view["selected"], {})
        self.assertNotIn("linked_calls", view)

    def test_opaque_ids_support_unicode_slashes_and_tildes(self):
        self.report["observations"][0]["id"] = "écriture/part~1"
        selector = "/observations/écriture~1part~01"
        view = select_evidence(self.report, [selector])
        self.assertEqual(view["selected"][selector]["id"], "écriture/part~1")

    def test_invalid_requests_fail_before_document_read(self):
        cases = [{"selectors": value} for value in ([], "calls/c1", [None], ["/calls"], ["/calls/"],
                 ["/calls/c1/status"], ["/calls/a~2"], ["/retry/0"], ["/declarations/not-a-digest"],
                 ["/calls/c1"] * 17)]
        cases += [{"expected_sha256": value} for value in (False, "A" * 64, "0" * 63)]
        cases += [{"result_index": value} for value in (True, -1, "0", 0.5)]
        with patch("skills.capabilities.evidence._read_document") as reader:
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    read_evidence(self.path, **kwargs)
        reader.assert_not_called()

    def test_corrupt_bindings_graph_and_nonfinite_data_do_not_leak_partial_records(self):
        corrupt = []
        value = deepcopy(self.report)
        value["declarations"][next(iter(value["declarations"]))]["contract_version"] = "0.9.0"
        corrupt.append(value)
        value = deepcopy(self.report)
        value["calls"][0]["parent_id"] = "c1"
        corrupt.append(value)
        value = deepcopy(self.report)
        value["observations"][0]["comparison"] = "supported"
        corrupt.append(value)
        value = deepcopy(self.report)
        value["network"][0]["duration_ms"] = float("nan")
        corrupt.extend([value, {}, None])
        for report in corrupt:
            with self.subTest(report_type=type(report).__name__):
                view = select_evidence(report, ["/network/n1"])
                self.assertEqual(view["selection_status"], "unavailable")
                self.assertIsNone(view["evidence_sha256"])
                self.assertEqual(view["selected"], {})

    def test_legacy_v1_preserves_unknown_network_coverage_and_empty_collections(self):
        self.report["schema"] = "botte.effect-observations/v1"
        self.report.pop("network")
        self.assertEqual(validate_report(self.report), [])
        self.assertNotIn("network", select_evidence(self.report)["index"])
        self.assertEqual(select_evidence(self.report, ["/network/n1"])["selection_status"], "not_found")
        self.report["observations"].clear()
        view = select_evidence(self.report)
        self.assertEqual(view["index"]["observations"], {})
        self.assertEqual(view["task_outcome"], "unverified")

    def test_saved_wrapper_requires_an_explicit_position_and_ignores_other_fields(self):
        document = {"effects_json": "/must/not/be/opened", "note": "Unrelated output must stay private.",
                    "results": [{"status": "blocked"}, {"effects_observed": self.report}]}
        self.save(document)
        self.assertEqual(read_evidence(self.path)["reason"], "result_index_required")
        self.assertEqual(read_evidence(self.path, result_index=0)["reason"], "not_observed")
        self.assertEqual(read_evidence(self.path, result_index=20)["reason"], "result_not_found")
        view = read_evidence(self.path, result_index=1)
        self.assertEqual(view["run_id"], self.report["run_id"])
        self.assertNotIn("Unrelated output", json.dumps(view))
        self.assertNotIn("must/not", json.dumps(view))

    def test_duplicate_json_oversized_missing_and_nonregular_documents_are_unavailable(self):
        for raw in ('{"results":[],"results":[]}', '{"value":NaN}', '[' * 1100, '{'):
            self.path.write_text(raw, encoding="utf-8")
            self.assertEqual(read_evidence(self.path)["reason"], "unreadable_document")
        self.save(self.report)
        with patch("skills.capabilities.evidence.MAX_DOCUMENT_BYTES", 10):
            self.assertEqual(read_evidence(self.path)["reason"], "unreadable_document")
        with patch("skills.capabilities.evidence.MAX_REPORT_BYTES", 10):
            self.assertEqual(read_evidence(self.path)["reason"], "evidence_too_large")
        self.assertEqual(read_evidence(self.path.parent)["reason"], "unreadable_document")
        self.assertEqual(read_evidence(self.path.parent / "missing.json")["reason"], "unreadable_document")
        if hasattr(os, "mkfifo"):
            fifo = self.path.parent / "fifo.json"
            os.mkfifo(fifo)
            self.assertEqual(read_evidence(fifo)["reason"], "unreadable_document")

    def test_reads_never_open_recorded_resources_or_start_work(self):
        original = self.path.read_bytes()
        with patch("skills.capabilities.evidence._read_document", wraps=evidence._read_document) as reader, \
             patch("skills.capabilities.effects.inspect_effects", side_effect=AssertionError("source inspection")), \
             patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("subprocess.run", side_effect=AssertionError("execution")), \
             patch("pathlib.Path.write_text", side_effect=AssertionError("write")):
            view = read_evidence(self.path, ["/observations/o1", "/network/n1"])
        reader.assert_called_once_with(self.path)
        self.assertEqual(view["selection_status"], "selected")
        self.assertEqual(self.path.read_bytes(), original)

    def test_file_replacement_during_read_returns_no_evidence(self):
        original_fstat = os.fstat
        inspected = 0
        def replace_after_read(fd):
            nonlocal inspected
            info = original_fstat(fd)
            inspected += 1
            if inspected == 2:
                replacement = self.path.with_suffix(".replacement")
                replacement.write_text(json.dumps(self.report), encoding="utf-8")
                replacement.replace(self.path)
            return info
        with patch("skills.capabilities.evidence.os.fstat", side_effect=replace_after_read):
            view = read_evidence(self.path, ["/calls/c1"])
        self.assertEqual(view["reason"], "unreadable_document")
        self.assertEqual(view["selected"], {})

    def test_mcp_source_boundaries_reject_traversal_and_file_or_directory_aliases(self):
        with patch("pathlib.Path.cwd", return_value=self.root):
            for source in (str(self.path), "fixture.json", ".botte/reports/../fixture.json",
                           ".botte//reports/fixture.json", ".botte/reports/./fixture.json",
                           ".botte/reports/nested/file.json", ".botte/reports/file.txt", None):
                with self.subTest(source=source), self.assertRaises(ValueError):
                    read_saved_evidence(source)
            alias = self.path.parent / "alias.json"
            try:
                alias.symlink_to(self.path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                read_saved_evidence(".botte/reports/alias.json")
            self.assertEqual(read_evidence(alias)["reason"], "unreadable_document")
            moved = self.root / "elsewhere"
            self.path.parent.rename(moved)
            self.path.parent.symlink_to(moved, target_is_directory=True)
            with self.assertRaises(ValueError):
                read_saved_evidence(".botte/reports/fixture.json")

    def test_lazy_mcp_read_and_dispatch_do_not_accept_extra_arguments(self):
        from skills.llm_mcp.lazy import find_tool, lazy_tool_list
        from skills.llm_mcp.server import TOOLS, handle
        self.assertNotIn("effect_evidence", {t["name"] for t in lazy_tool_list(TOOLS)})
        self.assertEqual(find_tool("effect_evidence", TOOLS)["matches"][0]["name"], "effect_evidence")
        args = {"source": ".botte/reports/fixture.json"}
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "effect_evidence", "arguments": args}}
        with patch("pathlib.Path.cwd", return_value=self.root):
            response = handle(request)
            indexed = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(indexed["selection_status"], "indexed")
            args.update(selectors=["/network/n1"], expected_sha256=indexed["evidence_sha256"])
            selected = json.loads(handle(request)["result"]["content"][0]["text"])
            self.assertEqual(selected["selected"]["/network/n1"]["http_status"], 202)
            self.assertEqual(selected["task_outcome"], "unverified")
            args["follow_resources"] = True
            self.assertTrue(handle(request)["result"]["isError"])

    def test_cli_exit_codes_and_review_after_digest_support_saved_handoffs(self):
        review = after({"status": "ran", "effects_observed": self.report}, before(None))
        self.assertEqual(review["evidence_sha256"], digest(self.report))
        self.assertEqual(review["run_id"], self.report["run_id"])
        self.save({"results": [{"review_after": review, "effects_observed": self.report}]})
        for flags, expected in (([], 0), (["--select", "/observations/o1"], 0),
                                (["--expect-sha256", "0" * 64], 1), (["--select", "/calls/0"], 1)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli(["evidence", str(self.path), "--result", "0", *flags]), expected)
            self.assertIn("selection_status", json.loads(output.getvalue()))
        for flags in (["--result", "-1"], ["--select", "/calls"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli(["evidence", str(self.path), *flags])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvidenceTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
