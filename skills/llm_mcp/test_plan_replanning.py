"""CLI/MCP boundaries for local checkpoint evidence and remaining-work advice."""

from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.conductor import test_replanning as fixtures
from skills.conductor.replanning import review_plan_replanning
from skills.llm_mcp.server import TOOLS
from skills.llm_mcp.test_plan_preferences import ROOT, call


@contextmanager
def fixture():
    # Synthetic checkpoint fixture; actual execution is covered by the separate pilot.
    case = fixtures.ReplanningTests("test_reuses_only_verified_evidence_and_preserves_full_order")
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


class ReplanningBoundaryTests(unittest.TestCase):
    def test_discoverable_read_only_closed_schema(self):
        definition = next(item for item in TOOLS if item["name"] == "review_plan_replanning")
        self.assertEqual(definition["annotations"], {
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        })
        self.assertFalse(definition["inputSchema"]["additionalProperties"])
        self.assertEqual(set(definition["inputSchema"]["required"]), {"request_json", "checkpoint_path"})
        self.assertIn("review_plan_replanning", call({"query": "review_plan_replanning"}, "find_tool")["content"][0]["text"])

    def test_mcp_matches_helper_without_writes_execution_network_or_telemetry(self):
        with fixture() as case:
            expected = case.review()
            before = snapshot(case.root)
            with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                    patch("socket.socket", side_effect=AssertionError("network")), \
                    patch("pathlib.Path.write_text", side_effect=AssertionError("write")), \
                    patch("skills.events.log_event", side_effect=AssertionError("telemetry")), \
                    patch("skills.conductor.verified.execute_verified", side_effect=AssertionError("executor")):
                response = call({"request_json": json.dumps(case.envelope()), "checkpoint_path": "run.json",
                                 "cwd": str(case.root)}, "review_plan_replanning")
            self.assertFalse(response.get("isError", False), response)
            self.assertEqual(json.loads(response["content"][0]["text"]), expected)
            self.assertEqual(snapshot(case.root), before)

    def test_stale_local_result_is_reported_with_no_retry(self):
        with fixture() as case:
            case.write("a.json", '{"ok":false}')
            before = snapshot(case.root)
            response = call({"request_json": json.dumps(case.envelope()), "checkpoint_path": "run.json",
                             "cwd": str(case.root)}, "review_plan_replanning")
            self.assertFalse(response.get("isError", False))
            report = json.loads(response["content"][0]["text"])
            self.assertEqual(report["reconciliation_action_ids"], ["a"])
            self.assertEqual(report["candidates"][0]["status"], "withheld")
            self.assertFalse(report["execution_authorized"])
            self.assertEqual(snapshot(case.root), before)

    def test_mcp_invalid_arguments_and_ambiguous_documents_fail(self):
        invalid = [{}, {"request_json": {}}, {"request_json": "{}", "checkpoint_path": ""},
                   {"request_json": "{}", "checkpoint_path": "run.json", "execute": True},
                   {"request_json": '{"schema":"a","schema":"b"}', "checkpoint_path": "run.json"},
                   {"request_json": '{"value":NaN}', "checkpoint_path": "run.json"},
                   {"request_json": "x" * (1048576 + 1), "checkpoint_path": "run.json"}]
        for args in invalid:
            with self.subTest(fields=list(args)):
                self.assertTrue(call(args, "review_plan_replanning")["isError"])
        with fixture() as case:
            good = {"request_json": json.dumps(case.envelope()), "checkpoint_path": "run.json", "cwd": str(case.root)}
            for change in ({"checkpoint_path": ""}, {"checkpoint_path": "../escape.json"},
                           {"checkpoint_path": str(case.root / "run.json")},
                           {"checkpoint_path": False}, {"cwd": []}):
                with self.subTest(change=change):
                    self.assertTrue(call({**good, **change}, "review_plan_replanning")["isError"])

    def test_actual_cli_from_outside_checkout_is_read_only(self):
        with fixture() as case, tempfile.TemporaryDirectory() as outside:
            source = case.root / "request.json"
            source.write_text(json.dumps(case.envelope()), encoding="utf-8")
            before = snapshot(case.root)
            expected = review_plan_replanning(case.envelope(), "run.json", cwd=str(case.root))
            result = subprocess.run([
                sys.executable, "-m", "skills.conductor.cli", "--review-plan-replanning", str(source),
                "--checkpoint", "run.json", "--project", str(case.root), "--json",
            ], cwd=outside, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(snapshot(case.root), before)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_cli_execution_and_out_of_mode_arguments_cannot_reach_executor(self):
        from skills.conductor.cli import main
        invalid = [
            ["goal", "--review-plan-replanning", "", "--execute", "--confirm"],
            ["--review-plan-replanning", "request.json"],
            ["--review-plan-replanning", "request.json", "--checkpoint", "run.json", "--resume"],
            ["--review-plan-replanning", "request.json", "--checkpoint", "run.json", "--dry-run"],
            ["--review-plan-replanning", "request.json", "--checkpoint", "run.json", "--max-checks", "2"],
            ["--review-plan-replanning", "request.json", "--checkpoint", "run.json", "--selection", "s.json"],
            ["--review-plan-replanning", "request.json", "--checkpoint", "run.json", "--compare-plans", "x.json"],
            ["--compare-plans", "request.json", "--checkpoint", "run.json"],
            ["--compare-plans", "request.json", "--project", "elsewhere"],
        ]
        for args in invalid:
            with self.subTest(args=args), patch("skills.conductor.cli._run_execute") as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()

    def test_actual_stdio_discovery_and_review_from_outside_checkout(self):
        with fixture() as case, tempfile.TemporaryDirectory() as outside:
            before = snapshot(case.root)
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "find_tool", "arguments": {"query": "review_plan_replanning"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                    "name": "review_plan_replanning", "arguments": {
                        "request_json": json.dumps(case.envelope()), "checkpoint_path": "run.json", "cwd": str(case.root)}}},
            ]
            result = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"],
                input="\n".join(json.dumps(item) for item in requests) + "\n", cwd=outside,
                env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([item["id"] for item in messages], [1, 2, 3])
            self.assertFalse(messages[-1]["result"].get("isError", False))
            self.assertEqual(json.loads(messages[-1]["result"]["content"][0]["text"]), case.review())
            self.assertEqual(snapshot(case.root), before)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
