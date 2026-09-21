"""Actual CLI/HTTP pilot across two isolated clients, without a homelab."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from skills.memory_hub.shared_http import AuthRegistry, MemoryHTTPServer
from skills.memory_hub.shared_service import MemoryService, Principal


class PilotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        identities = {}
        for actor, rights in (("writer", {"read", "write"}), ("reader", {"read"})):
            token = secrets.token_urlsafe(48)
            path = self.root / (actor + ".secret")
            with path.open("x", encoding="utf-8") as stream:
                stream.write(token)
            path.chmod(0o600)
            identities[hashlib.sha256(token.encode("ascii")).hexdigest()] = Principal(
                actor, frozenset({"pilot"}), frozenset(rights))
        self.server = MemoryHTTPServer(("127.0.0.1", 0), MemoryService(self.root / "store"),
                                       AuthRegistry(identities))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def cli(self, phase, actor="writer", extra=(), project="pilot"):
        args = [sys.executable, "-m", "scripts.action_memory_pilot", phase,
                "--url", f"http://127.0.0.1:{self.server.server_port}",
                "--token-file", str(self.root / (actor + ".secret")), "--project-id", project]
        result = subprocess.run(args + list(extra), capture_output=True, text=True,
                                encoding="utf-8", timeout=30,
                                env={**os.environ, "BOTTE_NN_AUTO_LABELS": "0"})
        return result.returncode, json.loads(result.stdout)

    def produce(self):
        folder = self.root / "producer"
        code, result = self.cli("produce", extra=("--directory", str(folder), "--execute"))
        self.assertEqual(code, 0, result)
        self.assertTrue(result["complete"])
        self.assertEqual((result["quantity"], result["total_cents"], result["executions"]), (13, 2740, 2))
        return folder

    def test_two_cli_identities_replay_stale_detection_and_read_only_handoff(self):
        folder = self.produce()
        before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        code, result = self.cli("consume", "reader", ("--handoff", str(folder / "handoff.json")))
        self.assertEqual(code, 0, result)
        self.assertTrue(result["private_episode_hidden"])
        self.assertTrue(result["shared_episode_unchanged"])
        self.assertEqual(result["commands_executed"], 0)
        after = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        retry = json.loads((folder / "capture-retry.json").read_text(encoding="utf-8"))
        self.assertTrue(retry["receipts"][0]["replayed"])

    def test_same_identity_cannot_claim_private_isolation(self):
        folder = self.produce()
        code, result = self.cli("consume", "writer", ("--handoff", str(folder / "handoff.json")))
        self.assertEqual(code, 1)
        self.assertEqual(result["check"], "private_episode_visible_use_a_different_identity")

    def test_preview_reads_no_token_and_existing_workspace_is_not_reexecuted(self):
        folder = self.root / "preview"
        code, result = self.cli("produce", "missing", ("--directory", str(folder)))
        self.assertEqual(code, 0, result)
        self.assertFalse(folder.exists())
        produced = self.produce()
        before = (produced / "executions.log").read_bytes()
        code, result = self.cli("produce", extra=("--directory", str(produced), "--execute"))
        self.assertEqual(code, 1)
        self.assertEqual(result["error_type"], "FileExistsError")
        self.assertEqual(before, (produced / "executions.log").read_bytes())

    def test_wrong_scope_and_tampered_handoff_do_not_pass(self):
        folder = self.produce()
        handoff_path = folder / "handoff.json"
        code, result = self.cli("consume", "reader", ("--handoff", str(handoff_path)), project="outside")
        self.assertEqual((code, result["check"]), (1, "handoff_project_mismatch"))
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff["shared_text_sha256"] = "0" * 64
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        code, result = self.cli("consume", "reader", ("--handoff", str(handoff_path)))
        self.assertEqual((code, result["check"]), (1, "shared_episode_changed"))
        code, result = self.cli("produce", extra=("--directory", str(self.root / "outside"), "--execute"), project="outside")
        self.assertEqual(code, 1)
        self.assertFalse((self.root / "outside").exists())


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PilotTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
