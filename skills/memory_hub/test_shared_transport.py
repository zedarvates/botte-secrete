"""HTTP and real stdio MCP acceptance; temporary loopback servers only."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
import queue
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from skills.memory_hub.cli import initialize
from skills.memory_hub.shared_contract import MAX_BODY, SCHEMAS, decode, encode
from skills.memory_hub.shared_http import AuthRegistry, MemoryHTTPClient, MemoryHTTPServer, read_token
from skills.memory_hub.shared_service import MemoryService, ServiceError
from skills.memory_hub.test_shared_service import record


@pytest.fixture
def pilot(tmp_path):
    root = tmp_path / "pilot"
    initialize(root, "pilot")
    server = MemoryHTTPServer(("127.0.0.1", 0), MemoryService(root / "data"), AuthRegistry.load(root / "auth.json"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield root, server, url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def client(pilot, actor="worker"):
    root, _, url = pilot
    return MemoryHTTPClient(url, read_token(root / f"{actor}.secret"))


def test_http_capture_and_mcp_process_read_share_the_same_store(pilot):
    root, _, url = pilot
    data = record("Synthetic work checkpoint", "agent", kind="checkpoint")
    written = client(pilot).call("checkpoint", {"project_id": "pilot", "key": "work",
                                "request_id": "capture-work", "record": data})
    assert written["quarantined"]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "memory_recall", "arguments": {"project_id": "pilot", "area": "observations"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "memory_recall", "arguments": {"project_id": "outside"}}},
    ]
    completed = subprocess.run([sys.executable, "-m", "skills.memory_hub.cli", "mcp", "--url", url,
                               "--token-file", str(root / "worker.secret")],
                              input=b"\n".join(encode(r) for r in requests) + b"\n", capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    responses = [decode(line) for line in completed.stdout.splitlines()]
    assert len(responses) == 4
    assert {t["name"] for t in responses[1]["result"]["tools"]} == {"memory_" + name for name in SCHEMAS}
    result = responses[2]["result"]
    assert result["structuredContent"]["entries"][0]["text"] == data["text"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert responses[3]["result"]["isError"] is True
    assert responses[3]["result"]["structuredContent"]["error"]["code"] == "forbidden"


def test_http_does_not_trust_a_claimed_user_source(pilot):
    with pytest.raises(ServiceError) as error:
        client(pilot).call("capture", {"project_id": "pilot", "key": "fake",
                          "request_id": "fake", "record": record()})
    assert error.value.status == 403


def test_two_http_identities_share_project_data_without_sharing_private_data(pilot):
    operator, worker = client(pilot, "operator"), client(pilot)
    for key, visibility in [("shared", "project"), ("private", "private")]:
        operator.call("capture", {"project_id": "pilot", "key": key, "request_id": key,
                                  "record": record(visibility=visibility)})
        for version, status in [(1, "review_active"), (2, "promoted")]:
            operator.call("review", {"project_id": "pilot", "key": key, "request_id": f"{key}-{version}",
                                     "expected_version": version, "new_status": status})
    assert [e["key"] for e in worker.call("recall", {"project_id": "pilot"})["entries"]] == ["shared"]


@pytest.mark.parametrize("override,status", [
    ({"Authorization": "Bearer invalid"}, 401),
    ({"Host": "evil.example"}, 403),
    ({"Origin": "https://evil.example"}, 403),
    ({"Content-Type": "text/plain"}, 415),
    ({"Content-Length": str(MAX_BODY + 1)}, 413),
    ({"Transfer-Encoding": "chunked"}, 400),
])
def test_http_rejects_invalid_transport_before_dispatch(pilot, override, status):
    root, server, _ = pilot
    headers = {"Authorization": "Bearer " + read_token(root / "worker.secret"), "Content-Type": "application/json"}
    headers.update(override)
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        conn.request("POST", "/v1/memory/recall", body=b'{"project_id":"pilot"}', headers=headers)
        response = conn.getresponse()
        assert response.status == status
        body = response.read()
        assert read_token(root / "worker.secret").encode() not in body
    finally:
        conn.close()


@pytest.mark.parametrize("body", [b'{"project_id":"pilot","project_id":"other"}',
                                  b'{"project_id":"pilot","limit":NaN}',
                                  b'[1,2]', b'{"project_id":"pilot","actor_id":"operator"}'])
def test_invalid_json_and_identity_injection_are_rejected(pilot, body):
    root, server, _ = pilot
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        conn.request("POST", "/v1/memory/recall", body=body,
                     headers={"Authorization": "Bearer " + read_token(root / "worker.secret"),
                              "Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 400
        response.read()
    finally:
        conn.close()


def test_auth_config_refuses_shared_tokens_and_permissions_on_secret(pilot):
    root, _, _ = pilot
    config = decode((root / "auth.json").read_text(encoding="utf-8"))
    config["principals"][1]["token_file"] = "worker.secret"
    path = root / "invalid-auth.json"
    path.write_text(encode(config).decode("utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="unique token"):
        AuthRegistry.load(path)
    if os.name != "nt":
        (root / "worker.secret").chmod(0o644)
        with pytest.raises(ValueError, match="only by its owner"):
            read_token(root / "worker.secret")


def test_no_remote_plaintext_endpoint_or_public_bind(pilot):
    root, _, _ = pilot
    with pytest.raises(ValueError, match="HTTPS"):
        MemoryHTTPClient("http://example.com", "x" * 32)
    with pytest.raises(ValueError, match="loopback"):
        MemoryHTTPServer(("0.0.0.0", 8766), MemoryService(root / "data"), AuthRegistry.load(root / "auth.json"))


def test_client_never_forwards_credentials_through_a_redirect():
    visited = []
    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            visited.append(self.path)
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/stolen")
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(ServiceError) as error:
            MemoryHTTPClient(f"http://127.0.0.1:{server.server_port}", "x" * 32).call("recall", {"project_id": "pilot"})
        assert error.value.code == "redirect_refused"
        assert visited == ["/v1/memory/recall"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("names", [[], ["operator"], ["Operator"], ["one", "one"],
                                  ["One", "one"], ["../escape"], ["bad:name"],
                                  ["a"] * 100, "worker"])
def test_invalid_worker_sets_fail_before_creating_files(tmp_path, names):
    with pytest.raises(ValueError):
        initialize(tmp_path / "invalid", "pilot", names)
    assert not (tmp_path / "invalid").exists()


def test_named_workers_get_separate_unprivileged_credentials(tmp_path):
    result = initialize(tmp_path / "pilot", "pilot", ["codex", "hermes"])
    config = decode((tmp_path / "pilot/auth.json").read_text(encoding="utf-8"))
    registry = AuthRegistry.load(tmp_path / "pilot/auth.json")
    tokens = []
    for name, filename in result["worker_token_files"].items():
        path = tmp_path / "pilot" / filename
        token = read_token(path)
        tokens.append(token)
        principal = registry.authenticate("Bearer " + token)
        assert principal.actor_id == name and principal.rights == {"read", "write", "forget"}
        assert token not in json.dumps(result) and token not in json.dumps(config)
    assert len(set(tokens)) == 2
    with pytest.raises(FileExistsError):
        initialize(tmp_path / "pilot", "pilot", ["codex", "hermes"])
    assert [read_token(tmp_path / "pilot" / name) for name in result["worker_token_files"].values()] == tokens
    if os.name != "nt":
        assert not (tmp_path / "pilot/auth.json").stat().st_mode & 0o077


def _cli(*args, timeout=60):
    return subprocess.run([sys.executable, "-m", "skills.memory_hub.cli", *map(str, args)],
                          capture_output=True, timeout=timeout)


@contextmanager
def _server_process(directory):
    with subprocess.Popen([sys.executable, "-u", "-m", "skills.memory_hub.cli", "serve",
                           "--directory", str(directory), "--port", "0"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stderr.readline()), daemon=True).start()
        try:
            line = ready.get(timeout=10).decode("utf-8")
            assert "listening on loopback port" in line, line
            yield "http://127.0.0.1:" + line.strip().split()[-1]
        finally:
            process.terminate()
            process.wait(timeout=10)


def test_cli_two_worker_acceptance_after_service_restart_preserves_other_records(tmp_path):
    root = tmp_path / "pilot"
    initialized = _cli("init", "--directory", root, "--project", "pilot",
                       "--agent", "codex", "--agent", "hermes")
    assert initialized.returncode == 0, initialized.stderr
    owner_path, peer_path = root / "agent-codex.secret", root / "agent-hermes.secret"
    with _server_process(root) as url:
        owner = MemoryHTTPClient(url, read_token(owner_path))
        owner.call("capture", {"project_id": "pilot", "key": "unrelated-fixture",
            "request_id": "unrelated-fixture", "record": record("Existing synthetic memory", "agent")})
    with _server_process(root) as url:
        completed = _cli("smoke", "--url", url, "--project", "pilot",
                         "--token-file", owner_path, "--peer-token-file", peer_path)
        assert completed.returncode == 0, completed.stdout
        report = decode(completed.stdout)
        assert report["passed"] and len(report["checks_passed"]) == 10
        assert report["cleanup"]["complete"] and report["cleanup"]["deleted_records"] == 2
        assert report["real_machine_pair_verified"] is False
        for path in root.glob("*.secret"):
            assert read_token(path).encode() not in completed.stdout + completed.stderr
        owner = MemoryHTTPClient(url, read_token(owner_path))
        history = owner.call("history", {"project_id": "pilot", "key": "unrelated-fixture"})
        assert history["revisions"][0]["version"] == 1
        configured = _cli("client-config", "--url", url, "--token-file", owner_path)
        assert configured.returncode == 0, configured.stderr
        bridge = decode(configured.stdout)["mcpServers"]["botte-shared-memory"]
        assert bridge["command"] == sys.executable and str(owner_path) in bridge["args"]
        assert read_token(owner_path).encode() not in configured.stdout
        assert Path(bridge["cwd"]).joinpath("skills/memory_hub/cli.py").is_file()


@pytest.fixture
def workers(tmp_path):
    root = tmp_path / "two-workers"
    initialize(root, "pilot", ["one", "two"])
    server = MemoryHTTPServer(("127.0.0.1", 0), MemoryService(root / "data"), AuthRegistry.load(root / "auth.json"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_smoke_cleans_a_committed_write_when_its_response_is_lost(workers, monkeypatch):
    from skills.memory_hub.smoke import run_smoke
    root, url = workers
    original_call = MemoryHTTPClient.call
    lost = []
    def lose_once(client, operation, args):
        result = original_call(client, operation, args)
        if operation == "checkpoint" and not lost:
            lost.append(True)
            raise ServiceError("unavailable", "Simulated lost response", 503)
        return result
    monkeypatch.setattr(MemoryHTTPClient, "call", lose_once)
    result = run_smoke(url, "pilot", root / "agent-one.secret", root / "agent-two.secret")
    assert not result["passed"] and result["failed_step"] == "shared_capture"
    assert result["cleanup"]["complete"] and result["cleanup"]["deleted_records"] == 1


def test_smoke_reports_pending_cleanup_without_exposing_transport_errors(workers, monkeypatch):
    from skills.memory_hub import smoke
    root, url = workers
    original_call = MemoryHTTPClient.call
    def fail_cleanup(client, operation, args):
        if operation == "forget":
            raise ServiceError("unavailable", "PRIVATE_TRANSPORT_CANARY", 503)
        return original_call(client, operation, args)
    monkeypatch.setattr(MemoryHTTPClient, "call", fail_cleanup)
    monkeypatch.setattr(smoke, "_peer_recall", lambda *a: (_ for _ in ()).throw(ValueError("PRIVATE_MCP_CANARY")))
    result = smoke.run_smoke(url, "pilot", root / "agent-one.secret", root / "agent-two.secret")
    assert not result["passed"] and not result["cleanup"]["complete"]
    assert len(result["cleanup"]["pending_keys"]) == 2
    assert "PRIVATE_" not in json.dumps(result)


def test_smoke_refuses_one_credential_used_twice(workers):
    from skills.memory_hub.smoke import run_smoke
    root, url = workers
    with pytest.raises(ValueError, match="two distinct"):
        run_smoke(url, "pilot", root / "agent-one.secret", root / "agent-one.secret")


def test_smoke_cleans_a_fixture_recreated_by_a_broken_replay_guard(workers, monkeypatch):
    import hashlib
    from skills.memory_hub.smoke import run_smoke
    from skills.memory_hub.store import MemoryStore
    root, url = workers
    original_call = MemoryHTTPClient.call
    def broken_replay(client, operation, args):
        try:
            return original_call(client, operation, args)
        except ServiceError as error:
            if operation != "checkpoint" or error.code != "forgotten":
                raise
            # Simulate a backend that loses precisely this fixture's deletion ledger.
            with MemoryStore(root / "data") as store:
                conn = store._conn("pilot")
                digest = hashlib.sha256(encode(["pilot", args["key"]])).hexdigest()
                conn.execute("DELETE FROM shared_tombstones WHERE key_digest = ?", (digest,))
                conn.commit()
            return original_call(client, operation, args)
    monkeypatch.setattr(MemoryHTTPClient, "call", broken_replay)
    result = run_smoke(url, "pilot", root / "agent-one.secret", root / "agent-two.secret")
    assert not result["passed"] and result["failed_step"] == "capture_replay_blocked"
    assert result["cleanup"]["complete"] and result["cleanup"]["deleted_records"] == 3
    with MemoryStore(root / "data") as store:
        assert store._conn("pilot").execute("SELECT COUNT(*) FROM memory_quarantine").fetchone()[0] == 0
