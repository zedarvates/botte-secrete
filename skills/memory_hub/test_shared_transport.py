"""HTTP and real stdio MCP acceptance; temporary loopback servers only."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
