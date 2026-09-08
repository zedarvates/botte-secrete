"""Real shared-store and subprocess checks for action-consequence memory."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from skills.conductor.test_verified import plan, step
from skills.conductor.verified import execute_verified, read_document
from skills.memory_hub.action_memory import (capture_report, episodes_for_report, recall_for_plan,
                                              run_with_memory, _identity, _request)
from skills.memory_hub.shared_service import MemoryService, Principal, ServiceError
from skills.memory_hub.store import MemoryStore
from skills.trajectory.outcome import load_outcomes
from skills.trajectory.quality import load_verified


class Client:
    def __init__(self, service, actor="alice", projects=("fixture",)):
        self.service = service
        self.principal = Principal(actor, frozenset(projects), frozenset({"read", "write", "forget"}))
        self.calls = []

    def call(self, operation, args):
        self.calls.append((operation, deepcopy(args)))
        return self.service.call(operation, args, self.principal)


class ActionMemoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "project"
        self.root.mkdir()
        self.store_path = Path(temp.name) / "shared"
        self.client = Client(MemoryService(self.store_path))
        self.write("input.txt", "6")
        self.write("worker.py", "import json\nfrom pathlib import Path\n"
                   "value=int(Path('input.txt').read_text(encoding='utf-8'))\n"
                   "Path('output.json').write_text(json.dumps({'value':value}), encoding='utf-8')\n")
        s = step("calculate", command="python worker.py NEVER_SHARE_ARGUMENT",
                 ensures=[{"kind": "json_equals", "path": "output.json", "pointer": "/value", "value": 6}])
        s["requires"] = [{"kind": "file_sha256", "path": "input.txt", "value": hashlib.sha256(b"6").hexdigest()}]
        s["source_hashes"] = {"worker.py": hashlib.sha256((self.root / "worker.py").read_bytes()).hexdigest()}
        self.plan = plan(s)
        self.plan["goal"] = "NEVER_SHARE_RAW_GOAL"

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def execute(self, **kwargs):
        return execute_verified(self.plan, cwd=str(self.root), confirm=True, **kwargs)

    def capture(self, report, **kwargs):
        return capture_report(self.plan, report, self.client, project_root=self.root,
                              project_id="fixture", **kwargs)

    def recall(self, **kwargs):
        return recall_for_plan(self.plan, self.client, project_root=self.root, project_id="fixture", **kwargs)

    def test_capture_is_idempotent_quarantined_and_links_unverified_quality_outcome(self):
        report = self.execute()
        self.assertTrue(report["complete"])
        first, replay = self.capture(report), self.capture(report)
        self.assertTrue(first["complete"])
        self.assertTrue(replay["receipts"][0]["replayed"])
        self.assertEqual(first["archive"], replay["archive"])
        self.assertEqual(read_document(self.root / first["archive"]), report)
        self.assertEqual(len(load_outcomes(self.root)), 1)
        self.assertFalse(load_outcomes(self.root)[0]["verified"])
        self.assertEqual(load_verified(self.root), [])
        with MemoryStore(self.store_path) as store:
            entry = store.get("fixture", first["receipts"][0]["key"], "alice")
            self.assertTrue(entry.quarantined)
            self.assertEqual(entry.version, 1)
            self.assertEqual(store.context_bundle("fixture", "alice"), [])
        encoded = json.dumps(self.client.calls)
        self.assertNotIn("NEVER_SHARE_RAW_GOAL", encoded)
        self.assertNotIn("NEVER_SHARE_ARGUMENT", encoded)

    def test_recall_rechecks_inputs_and_detects_stale_output_without_running(self):
        self.capture(self.execute())
        with patch("skills.conductor.verified._default_runner") as runner:
            fresh = self.recall()["steps"][0]["memories"][0]
            self.write("input.txt", "7")
            stale = self.recall()["steps"][0]["memories"][0]
        runner.assert_not_called()
        self.assertEqual(fresh["assessment"], "local_checks_match")
        self.assertEqual(stale["assessment"], "stale")
        self.assertTrue(any(not c["passed"] for c in stale["checks_now"]))
        self.assertEqual(stale["causal_attribution"], "not_assessed")

    def test_context_and_contract_changes_are_reported_before_file_reads(self):
        self.capture(self.execute())
        for expected in ("context_changed", "contract_changed", "different_action"):
            changed = deepcopy(self.plan)
            if expected == "context_changed":
                changed["context"] = "another-host-revision"
            elif expected == "contract_changed":
                changed["steps"][0]["ensures"][0]["value"] = 7
            else:
                changed["steps"][0]["command"] = "python another.py"
            with patch("skills.memory_hub.action_memory._check") as check:
                result = recall_for_plan(changed, self.client, project_root=self.root, project_id="fixture")
            check.assert_not_called()
            self.assertEqual(result["steps"][0]["memories"][0]["assessment"], expected)

    def test_resumption_keeps_earlier_evidence_and_does_not_repeat_writes(self):
        first = run_with_memory(self.plan, self.client, project_root=self.root,
                                project_id="fixture", checkpoint="run.json", confirm=True, dry_run=False)
        archive = self.root / first["memory_after"]["archive"]
        original = archive.read_bytes()
        with patch("skills.conductor.verified._default_runner") as runner:
            resumed = run_with_memory(self.plan, self.client, project_root=self.root,
                                      project_id="fixture", checkpoint="run.json", resume=True, dry_run=False)
        runner.assert_not_called()
        self.assertTrue(resumed["execution"]["complete"])
        self.assertTrue(resumed["execution"]["results"][0]["reused"])
        self.assertEqual(archive.read_bytes(), original)
        self.assertNotEqual(first["memory_after"]["archive"], resumed["memory_after"]["archive"])

    def test_changed_source_is_stale_and_unbound_source_is_never_called_current(self):
        self.capture(self.execute())
        self.write("worker.py", "changed code")
        self.assertEqual(self.recall()["steps"][0]["memories"][0]["assessment"], "stale")
        self.plan["steps"][0]["source_hashes"] = {}
        report = self.execute(runner=lambda *a: (0, "existing artifact"))
        self.capture(report)
        statuses = {m["assessment"] for m in self.recall()["steps"][0]["memories"]}
        self.assertIn("unbound_sources", statuses)

    def test_transport_retry_captures_only_and_preserves_deletion_tombstone(self):
        report = self.execute()
        real = self.client.call
        self.client.call = lambda *a: (_ for _ in ()).throw(ConnectionError("offline"))
        pending = self.capture(report)
        self.assertFalse(pending["complete"])
        self.assertEqual(len(pending["pending"]), 1)
        self.client.call = real
        with patch("skills.conductor.verified._default_runner") as runner:
            complete = self.capture(read_document(self.root / pending["archive"]))
        runner.assert_not_called()
        self.assertTrue(complete["complete"])
        key = complete["receipts"][0]["key"]
        self.client.call("forget", {"project_id": "fixture", "key": key,
                                    "request_id": "forget-episode", "expected_version": 1})
        forgotten = self.capture(report)
        self.assertFalse(forgotten["complete"])
        self.assertEqual(forgotten["pending"], [key])

    def test_private_and_project_scope_survive_adapter(self):
        self.capture(self.execute())
        bob = Client(self.client.service, "bob")
        result = recall_for_plan(self.plan, bob, project_root=self.root, project_id="fixture")
        self.assertEqual(result["steps"][0]["memories"], [])
        with self.assertRaises(ServiceError):
            recall_for_plan(self.plan, bob, project_root=self.root, project_id="another-project")

    def test_foreign_paths_in_memory_never_choose_local_read_targets(self):
        episode = episodes_for_report(self.plan, self.execute())[0]
        episode["expected"]["requires"][0]["path"] = "../../credentials.txt"
        episode["id"] = _identity(episode)
        self.client.call("capture", _request(episode, "fixture", "private"))
        from skills.memory_hub.action_memory import _check
        with patch("skills.memory_hub.action_memory._check", wraps=_check) as check:
            self.recall()
        paths = [c["path"] for call in check.call_args_list for c in call.args[1]]
        self.assertEqual(paths, ["input.txt", "output.json"])

    def test_bad_identity_is_ignored_and_does_not_recheck_files(self):
        episode = episodes_for_report(self.plan, self.execute())[0]
        episode["action"]["command_sha256"] = "0" * 64
        self.client.call("capture", _request(episode, "fixture", "private"))
        with patch("skills.memory_hub.action_memory._check") as check:
            result = self.recall()
        check.assert_not_called()
        self.assertEqual(result["invalid_entries"], 1)

    def test_repeated_unmet_condition_counts_distinct_runs_not_replayed_captures(self):
        for _ in range(3):
            report = self.execute(runner=lambda *a: (0, "no artifact"))
            self.capture(report)
            self.capture(report)
        result = self.recall()
        self.assertEqual(len(result["review_candidates"]), 1)
        self.assertEqual(result["review_candidates"][0]["distinct_runs"], 3)
        self.assertFalse(result["review_candidates"][0]["validated_improvement"])
        self.assertEqual(load_verified(self.root), [])

    def test_invalid_or_preview_report_has_no_capture_side_effects(self):
        report = self.execute(dry_run=True)
        with self.assertRaises(ValueError):
            self.capture(report)
        report = self.execute()
        report["plan_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.capture(report)
        self.assertEqual(self.client.calls, [])
        self.assertFalse((self.root / ".botte/action-evidence").exists())

    def test_preview_needs_no_credentials_and_writes_no_memory_or_checkpoint(self):
        from skills.memory_hub.action_cli import dispatch
        with patch("skills.memory_hub.action_cli.configured_client") as client:
            result = dispatch("run", {"plan": self.plan, "project": str(self.root),
                                       "project_id": "fixture", "checkpoint": "run.json"})
        client.assert_not_called()
        self.assertEqual(result["execution"]["mode"], "dry_run")
        self.assertFalse((self.root / "run.json").exists())
        self.assertFalse(self.store_path.exists())

    def test_memory_outage_does_not_repeat_or_hide_executed_work(self):
        self.client.call = lambda *a: (_ for _ in ()).throw(ConnectionError("offline"))
        result = run_with_memory(self.plan, self.client, project_root=self.root,
                                 project_id="fixture", checkpoint="run.json", confirm=True, dry_run=False)
        self.assertTrue(result["execution"]["complete"])
        self.assertTrue(result["memory_before"]["unavailable"])
        self.assertFalse(result["memory_after"]["complete"])
        self.assertTrue((self.root / result["memory_after"]["archive"]).exists())

    def test_real_authenticated_http_and_host_mcp_capture_recall_roundtrip(self):
        import os
        import secrets
        import threading
        from skills.memory_hub.shared_http import AuthRegistry, MemoryHTTPServer, MemoryHTTPClient
        from skills.llm_mcp.server import handle
        token = secrets.token_hex(32)
        self.write("worker-token.secret", token)
        (self.root / "worker-token.secret").chmod(0o600)
        auth = AuthRegistry({hashlib.sha256(token.encode("ascii")).hexdigest(): self.client.principal})
        report = self.execute()
        with MemoryHTTPServer(("127.0.0.1", 0), self.client.service, auth) as server:
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                with patch.dict(os.environ, {"BOTTE_MEMORY_URL": url,
                                             "BOTTE_MEMORY_TOKEN_FILE": str(self.root / "worker-token.secret")}):
                    def call(name, arguments):
                        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                           "params": {"name": name, "arguments": arguments}})
                        return json.loads(response["result"]["content"][0]["text"])
                    args = {"plan": self.plan, "project": str(self.root), "project_id": "fixture"}
                    captured = call("remember_skill_run", {**args, "report": report})
                    recalled = call("recall_action_memory", args)
                    self.assertTrue(captured.get("complete"), captured)
                    self.assertEqual(recalled["steps"][0]["memories"][0]["assessment"], "local_checks_match")
                    self.assertNotIn(token, json.dumps([captured, recalled]))
                with self.assertRaises(ServiceError):
                    MemoryHTTPClient(url, "x" * 64).call("recall", {"project_id": "fixture"})
            finally:
                server.shutdown()
                thread.join(2)

    def test_episode_schema_accepts_real_report_and_rejects_unknown_instruction(self):
        try:
            from jsonschema import Draft202012Validator, ValidationError
        except ImportError:
            self.skipTest("optional jsonschema test dependency unavailable")
        path = Path(__file__).resolve().parents[2] / "docs/schemas/action-consequence.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        episode = episodes_for_report(self.plan, self.execute())[0]
        validator.validate(episode)
        episode["execute"] = "do something"
        with self.assertRaises(ValidationError):
            validator.validate(episode)

    def test_episode_boolean_fields_reject_truthy_strings(self):
        from skills.memory_hub.action_contract import validate_episode
        original = episodes_for_report(self.plan, self.execute())[0]
        for field in ("started", "sources_bound", "passed"):
            episode = deepcopy(original)
            if field == "started":
                episode[field] = "true"
            elif field == "sources_bound":
                episode["expected"][field] = "true"
            else:
                episode["observed"]["checks"][0][field] = "true"
            with self.assertRaises(ValueError):
                validate_episode(episode)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ActionMemoryTests)
    result = unittest.TextTestRunner().run(suite)
    failures = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failures - len(result.skipped)} passed, {failures} failed, {len(result.skipped)} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
