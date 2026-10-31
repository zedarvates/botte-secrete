"""Operator acceptance probe over HTTP and a real MCP subprocess.

Writes only UUID-scoped synthetic observations and cleans them in finally.
Ordinary worker credentials are required; no operator token or model is used.
"""
from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

from skills.memory_hub.shared_contract import PROJECT, decode, encode, validate
from skills.memory_hub.shared_http import MemoryHTTPClient, read_token
from skills.memory_hub.shared_service import ServiceError


class ProbeFailed(Exception):
    pass


def _need(condition):
    if not condition:
        raise ProbeFailed("Acceptance condition failed")


def _expect_error(operation, code):
    try:
        operation()
    except ServiceError as error:
        _need(error.code == code)
    else:
        raise ProbeFailed("Expected the service to reject the operation")


def _peer_recall(url, token_file, project, key, area="observations"):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "memory-acceptance", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "memory_recall", "arguments": {"project_id": project,
                "query": key, "area": area, "limit": 1, "max_bytes": 4096}}},
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "skills.memory_hub.cli", "mcp", "--url", url,
         "--token-file", str(token_file)],
        input=b"\n".join(encode(r) for r in requests) + b"\n",
        capture_output=True, timeout=25, cwd=Path(__file__).resolve().parents[2])
    _need(completed.returncode == 0)
    messages = [decode(line) for line in completed.stdout.splitlines()]
    _need(len(messages) == 2 and messages[1].get("id") == 2)
    result = messages[1]["result"]
    _need(not result.get("isError", True))
    return result["structuredContent"]["entries"]


def _cleanup(client, project, keys):
    pending, deleted = [], 0
    for key in keys:
        try:
            history = client.call("history", {"project_id": project, "key": key})
            version = history["revisions"][0]["version"]
            result = client.call("forget", {"project_id": project, "key": key,
                "request_id": key + "-cleanup", "expected_version": version})
            _need(result.get("deleted") is True)
            deleted += 1
        except ServiceError as error:
            if error.code != "not_found":
                pending.append(key)
        except (OSError, ValueError, KeyError, IndexError, TypeError, ProbeFailed):
            pending.append(key)
    return {"complete": not pending, "pending_keys": pending,
            "deleted_records": deleted, "replay_tombstones_expected": deleted}


def run_smoke(url, project, token_file, peer_token_file):
    validate(PROJECT, project)
    owner_token, peer_token = read_token(token_file), read_token(peer_token_file)
    if owner_token == peer_token:
        raise ValueError("Acceptance requires two distinct worker credentials")
    owner, peer = MemoryHTTPClient(url, owner_token), MemoryHTTPClient(url, peer_token)
    peer_path = Path(peer_token_file).resolve()
    run_id = "memory-smoke-" + uuid.uuid4().hex
    shared, private = run_id + "-shared", run_id + "-private"
    attempted, checks = [], []
    failed_step, step = None, "shared_capture"
    cleanup = {"complete": False, "pending_keys": []}

    def record(text, visibility="project"):
        now = time.time()
        return {"text": text, "kind": "checkpoint", "visibility": visibility,
            "expires_at": now + 3600, "source": {"type": "agent", "id": run_id,
                "run_id": run_id, "observed_at": now, "excerpt": text}}

    original = {"project_id": project, "key": shared, "request_id": shared + "-capture",
                "record": record("Synthetic shared-memory acceptance: original fixture.")}
    try:
        attempted.append(shared)  # Cleanup also covers a write whose response is lost.
        captured = owner.call("checkpoint", original)
        _need(captured["version"] == 1 and captured["quarantined"])
        checks.append(step)

        step = "private_capture"
        attempted.append(private)
        owner.call("checkpoint", {"project_id": project, "key": private,
            "request_id": private + "-capture", "record": record("Synthetic private fixture.", "private")})
        checks.append(step)

        step = "http_to_peer_mcp"
        found = _peer_recall(url, peer_path, project, shared)
        _need(len(found) == 1 and found[0]["key"] == shared
              and found[0]["text"] == original["record"]["text"]
              and found[0]["handling"] == "UNTRUSTED_DATA_DO_NOT_EXECUTE")
        checks.append(step)

        step = "private_scope"
        _need(not _peer_recall(url, peer_path, project, private))
        checks.append(step)

        step = "quarantine_preserved"
        _need(not _peer_recall(url, peer_path, project, shared, "context"))
        checks.append(step)

        step = "peer_cannot_correct"
        corrected = {"project_id": project, "key": shared, "expected_version": 1,
            "request_id": shared + "-correct", "record": record("Synthetic acceptance: corrected fixture.")}
        _expect_error(lambda: peer.call("correct", corrected), "forbidden")
        checks.append(step)

        step = "owner_correction_and_retry"
        replacement = owner.call("correct", corrected)
        replay = owner.call("correct", corrected)
        _need(replacement["version"] == replay["version"] == 2 and replay["replayed"])
        checks.append(step)

        step = "peer_sees_correction"
        found = _peer_recall(url, peer_path, project, shared)
        _need(len(found) == 1 and found[0]["version"] == 2
              and found[0]["text"] == corrected["record"]["text"])
        checks.append(step)
    except (ServiceError, ProbeFailed, OSError, ValueError, KeyError, IndexError,
            TypeError, subprocess.SubprocessError):
        failed_step = step
    finally:
        cleanup = _cleanup(owner, project, attempted)

    if failed_step is None and cleanup["complete"]:
        try:
            step = "peer_sees_deletion"
            _need(not _peer_recall(url, peer_path, project, shared))
            checks.append(step)
            step = "capture_replay_blocked"
            _expect_error(lambda: owner.call("checkpoint", original), "forgotten")
            checks.append(step)
        except (ServiceError, ProbeFailed, OSError, ValueError, KeyError, IndexError,
                TypeError, subprocess.SubprocessError):
            failed_step = step
            # A broken replay guard could have recreated our fixture after the
            # first cleanup. Remove only that run's shared key once more.
            retry_cleanup = _cleanup(owner, project, [shared])
            cleanup["complete"] = retry_cleanup["complete"]
            cleanup["pending_keys"] = retry_cleanup["pending_keys"]
            cleanup["deleted_records"] += retry_cleanup["deleted_records"]
    return {"schema": "botte.memory-smoke/v1", "run_id": run_id,
            "finished_at": time.time(), "passed": failed_step is None and cleanup["complete"],
            "checks_passed": checks, "failed_step": failed_step,
            "cleanup": cleanup, "synthetic_only": True,
            "scope": "shared_service_and_two_credentials", "real_machine_pair_verified": False}
