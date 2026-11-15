"""Selection/handoff boundaries through actual CLI and MCP interfaces."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.conductor.preferences import propose_plans
from skills.conductor.selection import select_plan
from skills.llm_mcp.server import TOOLS, handle
from skills.llm_mcp.test_plan_preferences import ROOT, call, example


def explicit_plan(request, candidate_id):
    actions = {action["id"]: action for action in request["actions"]}
    candidate = next(item for item in request["candidates"] if item["id"] == candidate_id)
    return {
        "schema": "botte.skill-plan/v1", "goal": "Synthetic interface fixture",
        "context": "selection-handoff-test-v1",
        "steps": [{"id": aid, "capability": "fixture", "local": True,
                   "command": "python -c \"raise SystemExit('fixture must not run')\"",
                   "needs": list(actions[aid]["needs"]), "requires": [], "ensures": [],
                   "observes": [], "source_hashes": {}}
                  for aid in candidate["steps"]],
    }


def inputs():
    request = example()
    digest = propose_plans(request)["input_digest"]
    selection = select_plan(request, "rapid", digest)
    plan = explicit_plan(request, "rapid")
    return request, digest, selection, plan


class PlanSelectionBoundaryTests(unittest.TestCase):
    def test_both_tools_are_discoverable_read_only_and_closed_world(self):
        for name in ("select_plan", "prepare_plan_handoff"):
            definition = next(item for item in TOOLS if item["name"] == name)
            self.assertEqual(definition["annotations"], {
                "readOnlyHint": True, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False,
            })
            self.assertFalse(definition["inputSchema"]["additionalProperties"])
            self.assertIn(name, call({"query": name}, "find_tool")["content"][0]["text"])

    def test_mcp_selection_keeps_choice_and_recommendation_distinct(self):
        request, digest, selection, _ = inputs()
        response = call({"request_json": json.dumps(request), "candidate_id": "rapid",
                         "expected_input_digest": digest}, "select_plan")
        self.assertFalse(response.get("isError", False))
        receipt = json.loads(response["content"][0]["text"])
        self.assertEqual(receipt, selection)
        self.assertEqual(receipt["recommended_candidate_id"], "economical")
        self.assertEqual(receipt["selected_candidate_id"], "rapid")
        self.assertFalse(receipt["execution_authorized"])
        self.assertFalse(receipt["claim"]["choice_authority_verified"])

    def test_mcp_rejects_stale_absent_and_extra_selection_arguments(self):
        request, digest, _, _ = inputs()
        valid = {"request_json": json.dumps(request), "candidate_id": "rapid",
                 "expected_input_digest": digest}
        for changes in ({"expected_input_digest": "0" * 64}, {"candidate_id": "missing"},
                        {"candidate_id": True}, {"execute": True},
                        {"expected_input_digest": None}):
            with self.subTest(changes=changes):
                self.assertTrue(call({**valid, **changes}, "select_plan")["isError"])

    def test_mcp_handoff_matches_library_without_running_or_writing(self):
        from skills.conductor.handoff import prepare_plan_handoff
        request, _, receipt, plan = inputs()
        expected = prepare_plan_handoff(request, receipt, plan)
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("storage")), \
                patch("skills.events.log_event", side_effect=AssertionError("telemetry")), \
                patch("skills.conductor.verified.execute_verified", side_effect=AssertionError("executor")):
            response = call({"request_json": json.dumps(request), "selection_json": json.dumps(receipt),
                             "execution_plan_json": json.dumps(plan)}, "prepare_plan_handoff")
        self.assertFalse(response.get("isError", False))
        packet = json.loads(response["content"][0]["text"])
        self.assertEqual(packet, expected)
        self.assertEqual(packet["status"], "prepared_unverified")
        self.assertEqual(packet["execution_plan"], plan)
        self.assertFalse(packet["execution_authorized"])

    def test_mcp_handoff_rejects_ambiguous_documents_and_extra_arguments(self):
        request, _, receipt, plan = inputs()
        valid = {"request_json": json.dumps(request), "selection_json": json.dumps(receipt),
                 "execution_plan_json": json.dumps(plan)}
        for changes in ({"execute": True}, {"selection_json": {}},
                        {"execution_plan_json": '{"schema":"a","schema":"b"}'},
                        {"execution_plan_json": '{"value":NaN}'},
                        {"request_json": "x" * (1048576 + 1)},
                        {"selection_json": "[" * 1500 + "]" * 1500}):
            with self.subTest(fields=list(changes)):
                self.assertTrue(call({**valid, **changes}, "prepare_plan_handoff")["isError"])

    def run_cli(self, mode):
        request, digest, receipt, plan = inputs()
        with tempfile.TemporaryDirectory() as directory:
            for filename, data in (("request.json", request), ("selection.json", receipt), ("plan.json", plan)):
                (Path(directory) / filename).write_text(json.dumps(data), encoding="utf-8")
            flags = (["--candidate", "rapid", "--input-digest", digest] if mode == "--select-plan"
                     else ["--selection", "selection.json", "--execution-plan", "plan.json"])
            result = subprocess.run(
                [sys.executable, "-m", "skills.conductor.cli", mode, "request.json", *flags, "--json"],
                cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             ["plan.json", "request.json", "selection.json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_cli_selection_reads_request_and_prints_receipt_only(self):
        self.assertEqual(self.run_cli("--select-plan"), inputs()[2])

    def test_cli_handoff_reads_supplied_documents_and_prints_unexecuted_packet(self):
        from skills.conductor.handoff import prepare_plan_handoff
        request, _, receipt, plan = inputs()
        self.assertEqual(self.run_cli("--prepare-plan-handoff"), prepare_plan_handoff(request, receipt, plan))

    def test_cli_empty_paths_cannot_reach_executor(self):
        from skills.conductor.cli import main
        for mode in ("--select-plan", "--prepare-plan-handoff"):
            with patch("skills.conductor.cli._run_execute", return_value=77) as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(["test goal", mode, "", "--execute", "--confirm"])
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()

    def test_cli_rejects_missing_mixed_and_out_of_mode_choice_arguments(self):
        from skills.conductor.cli import main
        invalid = [
            ["--select-plan", "request.json"],
            ["--select-plan", "request.json", "--candidate", "rapid", "--input-digest", "0" * 64,
             "--selection", "selection.json"],
            ["--prepare-plan-handoff", "request.json"],
            ["--prepare-plan-handoff", "request.json", "--candidate", "rapid"],
            ["goal", "--execute", "--confirm", "--candidate", "rapid"],
            ["--propose-plans", "request.json", "--selection", "selection.json"],
            ["--select-plan", "request.json", "--prepare-plan-handoff", "request.json"],
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), \
                    patch("skills.conductor.cli._run_execute") as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(arguments)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()

    def test_stdio_selection_and_handoff_roundtrip(self):
        request, digest, receipt, plan = inputs()
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "select_plan",
             "arguments": {"request_json": json.dumps(request), "candidate_id": "rapid",
                           "expected_input_digest": digest}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "prepare_plan_handoff",
             "arguments": {"request_json": json.dumps(request), "selection_json": json.dumps(receipt),
                           "execution_plan_json": json.dumps(plan)}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-m", "skills.llm_mcp.server"],
                input="\n".join(json.dumps(item) for item in requests) + "\n", cwd=directory,
                env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            replies = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual([item["id"] for item in replies], [1, 2, 3])
            self.assertEqual(json.loads(replies[1]["result"]["content"][0]["text"]), receipt)
            packet = json.loads(replies[2]["result"]["content"][0]["text"])
            self.assertEqual(packet["selected_candidate_id"], "rapid")
            self.assertEqual(packet["execution_plan"], plan)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
