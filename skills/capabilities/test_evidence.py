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
from skills.capabilities.review import after, attach_results, before


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

    def execution(self):
        return {"goal": "Fixture café", "mode": "safe_only",
                "summary": {"ran": 1, "failed": 1, "blocked": 1, "skipped": 1},
                "results": [{"order": 7, "capability": "worker", "command": "fixture operation",
                             "status": "ran", "exit_code": 0, "effects_observed": self.report,
                             "review_before": before({"status": "declared", "contract": self.contract}),
                             "review_after": {"task_outcome": "verified", "attention": []},
                             "note": "Deferred output tail."},
                            {"order": 7, "capability": "worker", "command": "fixture failure",
                             "status": "failed", "exit_code": 1},
                            {"capability": "worker", "command": "fixture gated",
                             "status": "blocked", "exit_code": None},
                            {"capability": "worker", "command": "fixture <placeholder>",
                             "status": "skipped", "exit_code": None}]}

    def test_overview_preserves_every_position_and_recomputes_outcome_cues(self):
        document = self.execution()
        self.save(document)
        original = self.path.read_bytes()
        view = read_evidence(self.path, overview=True)
        self.assertEqual(view["selection_status"], "overview")
        self.assertEqual(view["summary"], document["summary"])
        self.assertEqual([r["result_index"] for r in view["results"]], [0, 1, 2, 3])
        self.assertEqual([r["status"] for r in view["results"]], ["ran", "failed", "blocked", "skipped"])
        review = view["results"][0]["review_after"]
        self.assertEqual(review["coverage"], "partial")
        self.assertEqual(review["task_outcome"], "unverified")
        self.assertIn("nested_failure", review["attention"])
        self.assertFalse(review["declaration_changed"])
        self.assertEqual(review["next_action"], "inspect_state_before_retry")
        self.assertEqual(view["results"][1]["review_after"]["coverage"], "not_observed")
        self.assertEqual(view["results"][1]["review_after"]["next_action"], "inspect_state_before_retry")
        self.assertEqual(view["results"][2]["review_after"]["task_outcome"], "not_run")
        for omitted in ("Deferred output tail", "Unrequested retained", str(self.output)):
            self.assertNotIn(omitted, json.dumps(view))
        self.assertEqual(self.path.read_bytes(), original)

    def test_overview_rejects_invalid_metadata_without_omitting_steps(self):
        cases = [self.report, {}, {**self.execution(), "results": []},
                 {**self.execution(), "mode": "unknown"}, {**self.execution(), "goal": None},
                 {**self.execution(), "mode": "dry_run"}]
        for field, value in (("status", []), ("status", "success"), ("exit_code", True),
                             ("exit_code", 2), ("command", None)):
            document = self.execution()
            document["results"][0][field] = value
            cases.append(document)
        for count in (True, 0):
            document = self.execution()
            document["summary"]["ran"] = count
            cases.append(document)
        document = self.execution()
        document["results"] *= 33
        cases.append(document)
        for document in cases:
            self.save(document)
            view = read_evidence(self.path, overview=True)
            self.assertEqual(view["selection_status"], "unavailable")
            self.assertNotIn("results", view)

    def test_overview_keeps_corrupt_or_oversized_evidence_unknown_per_step(self):
        for observed in ({}, {**self.report, "observations": [
                {**self.report["observations"][0], "effect_ref": "/expected_effects/" + "9" * 5000}]}):
            document = self.execution()
            document["results"][0]["effects_observed"] = observed
            document["results"][2]["effects_observed"] = {}
            self.save(document)
            view = read_evidence(self.path, overview=True)
            self.assertEqual(len(view["results"]), 4)
            review = view["results"][0]["review_after"]
            self.assertEqual(review["coverage"], "invalid_evidence")
            self.assertNotIn("evidence_ref", review)
            self.assertEqual(review["task_outcome"], "unverified")
            self.assertEqual(view["results"][2]["review_after"]["task_outcome"], "unverified")
        self.save(self.execution())
        with patch("skills.capabilities.review.MAX_REPORT_BYTES", 10):
            view = read_evidence(self.path, overview=True)
        review = view["results"][0]["review_after"]
        self.assertEqual(review["coverage"], "invalid_evidence")
        self.assertIn("observation_report_too_large", review["attention"])
        self.assertNotIn("evidence_ref", review)

    def test_overview_fingerprints_wrapper_metadata_separately_from_evidence(self):
        document = self.execution()
        self.save(document)
        first = read_evidence(self.path, overview=True)
        self.assertEqual(first["document_sha256"], digest(document))
        self.path.write_text(json.dumps(document, sort_keys=True, indent=4), encoding="utf-8")
        self.assertEqual(read_evidence(self.path, overview=True)["document_sha256"], first["document_sha256"])
        document["results"][0]["note"] = "Changed deferred metadata."
        self.save(document)
        second = read_evidence(self.path, overview=True)
        self.assertNotEqual(first["document_sha256"], second["document_sha256"])
        self.assertEqual(first["results"][0]["review_after"]["evidence_ref"],
                         second["results"][0]["review_after"]["evidence_ref"])

    def test_overview_exposes_conflicting_process_evidence_without_claiming_not_run(self):
        document = self.execution()
        document["results"][0].update(status="blocked", exit_code=None)
        document["summary"].update(ran=0, blocked=2)
        self.save(document)
        review = read_evidence(self.path, overview=True)["results"][0]["review_after"]
        self.assertIn("process_evidence_mismatch", review["attention"])
        self.assertEqual(review["coverage"], "partial")
        self.assertEqual(review["task_outcome"], "unverified")
        self.assertEqual(review["next_action"], "inspect_state_before_retry")
        self.assertIn("evidence_ref", review)

    def test_overview_requires_explicit_mode_and_rejects_mixed_queries_before_read(self):
        self.save(self.execution())
        self.assertEqual(read_evidence(self.path)["reason"], "result_index_required")
        with patch("skills.capabilities.evidence._read_document") as reader:
            for kwargs in ({"overview": 1}, {"overview": "true"}, {"overview": None},
                           {"overview": True, "selectors": ["/calls/c1"]},
                           {"overview": True, "result_index": 0},
                           {"overview": True, "expected_sha256": "0" * 64}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    read_evidence(self.path, **kwargs)
        reader.assert_not_called()

    def test_live_and_saved_reviews_agree_on_invalid_and_conflicting_evidence(self):
        for status, observed in (("ran", self.report), ("blocked", self.report),
                                 ("blocked", {}), ("failed", self.report)):
            with self.subTest(status=status, valid=bool(observed)):
                document = self.execution()
                step = document["results"][0]
                step.update(status=status, exit_code={"ran": 0, "blocked": None, "failed": 1}[status],
                            effects_observed=observed)
                document["summary"]["ran"] -= 1
                document["summary"][status] += 1
                attach_results(document["results"], [row.get("review_before") for row in document["results"]])
                self.save(document)
                saved = read_evidence(self.path, overview=True)["results"][0]["review_after"]
                live = step["review_after"]
                if "evidence_ref" in saved:
                    self.assertEqual(saved["evidence_ref"]["expected_sha256"], live["evidence_sha256"])
                    saved["evidence_ref"] = "effects_observed"
                self.assertEqual(saved, live)

    def test_overview_reads_one_file_without_work_or_following_stored_paths(self):
        document = self.execution()
        document["effects_json"] = "/untrusted/redirect.json"
        self.save(document)
        with patch("skills.capabilities.evidence._read_document", wraps=evidence._read_document) as reader, \
             patch("skills.capabilities.effects.inspect_effects", side_effect=AssertionError("source read")), \
             patch("subprocess.run", side_effect=AssertionError("execution")), \
             patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("pathlib.Path.write_text", side_effect=AssertionError("write")):
            view = read_evidence(self.path, overview=True)
        reader.assert_called_once_with(self.path)
        self.assertEqual(view["selection_status"], "overview")
        self.assertNotIn("untrusted/redirect", json.dumps(view))

    def test_overview_mcp_references_roundtrip_and_detect_substitution(self):
        from skills.llm_mcp.server import handle
        self.save(self.execution())
        def call(args):
            response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "effect_evidence", "arguments": args}})
            self.assertFalse(response["result"].get("isError", False))
            return json.loads(response["result"]["content"][0]["text"])
        with patch("pathlib.Path.cwd", return_value=self.root):
            overview = call({"source": ".botte/reports/fixture.json", "overview": True})
            ref = overview["results"][0]["review_after"]["evidence_ref"]
            self.assertEqual(ref["source"], ".botte/reports/fixture.json")
            self.assertEqual(ref["result_index"], 0)
            self.assertEqual(call(ref)["selection_status"], "indexed")
            detail = call({**ref, "selectors": ["/network/n1"]})
            self.assertEqual(detail["selected"]["/network/n1"]["remote_effects"], "unknown")
            document = self.execution()
            replacement = deepcopy(self.report)
            replacement["run_id"] = "0" * 32
            document["results"][0]["effects_observed"] = replacement
            self.save(document)
            self.assertEqual(call(ref)["selection_status"], "changed")

    def test_overview_cli_success_means_read_success_despite_recorded_failures(self):
        self.save(self.execution())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli(["evidence", str(self.path), "--overview"]), 0)
        self.assertEqual(json.loads(output.getvalue())["summary"]["failed"], 1)
        self.save({})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli(["evidence", str(self.path), "--overview"]), 1)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            cli(["evidence", str(self.path), "--overview", "--result", "0"])
        self.assertEqual(error.exception.code, 2)

    def test_overview_reads_a_real_executor_report_saved_by_the_cli(self):
        from skills.capabilities.observations import _SESSION
        from skills.conductor import execute
        from skills.conductor.cli import main as conduct
        steps = [{"order": 1, "capability": "metrics", "command": "fixture analysis"},
                 {"order": 2, "capability": "unknown", "command": "fixture gated"}]
        def runner(*_):
            with _SESSION.get().call(self.skill, "fixture failure"):
                pass
            return 1, "fixture failure"
        report = execute({"goal": "Fixture", "steps": steps}, observe_effects=True,
                         review_effects=True, runner=runner)
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch("skills.conductor.cli.run_goal", return_value=report), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(conduct(["Fixture", "--execute", "--observe-effects",
                                          "--review-effects", "--json", "--save", "md"]), 1)
            saved = json.loads(output.getvalue())
            view = read_saved_evidence(saved["effects_json"], overview=True)
            self.assertEqual(view["summary"], {"ran": 0, "failed": 1, "blocked": 1, "skipped": 0})
            for step in view["results"]:
                ref = step["review_after"]["evidence_ref"]
                evidence_view = read_saved_evidence(**ref)
                self.assertEqual(evidence_view["selection_status"], "indexed")
                self.assertEqual(evidence_view["run_id"], step["review_after"]["run_id"])
        finally:
            os.chdir(previous)

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
