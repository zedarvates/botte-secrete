"""Optional, isolated Needle 2 router. Every output remains advisory.

The core imports only stdlib; cactus-needle belongs to the explicitly selected
worker interpreter. No downloads, function execution, or persistent sessions
across requests are permitted by this adapter.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import time

from skills.memory_hub.shared_contract import decode, encode, validate
from .base import ToolRouteResult, validate_route

MAX_TOOLS = 5
MAX_QUERY_BYTES = 512
MAX_RESPONSE_BYTES = 65_536


class Needle2ToolRouter:
    """One serial worker per router, with an explicit local native library.

    confidence_threshold is an experimental selection threshold, never an
    authorization or a calibrated guarantee on this domain.
    """

    def __init__(self, library_path=None, *, python_executable=None,
                 confidence_threshold=0.9, timeout=15.0):
        if (isinstance(confidence_threshold, bool)
                or not isinstance(confidence_threshold, (int, float))
                or not math.isfinite(confidence_threshold)
                or not 0 <= confidence_threshold <= 1):
            raise ValueError("confidence_threshold must be between zero and one")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or not 0 < timeout <= 60):
            raise ValueError("timeout must be positive and at most 60 seconds")
        self.library_path = Path(library_path).resolve() if library_path else None
        self.python_executable = str(python_executable or sys.executable)
        self.confidence_threshold, self.timeout = confidence_threshold, timeout
        self._process = None
        self._messages = None
        self._catalog = None
        self._lock = threading.Lock()
        self.startup_ms = None
        self.library_sha256 = None
        self.worker_runtime = None

    def _read_output(self, process, messages):
        try:
            while True:
                line = process.stdout.readline(MAX_RESPONSE_BYTES + 1)
                if not line or len(line) > MAX_RESPONSE_BYTES:
                    messages.put(None)
                    return
                messages.put(line)
        except (OSError, ValueError):
            messages.put(None)

    def _receive(self):
        try:
            line = self._messages.get(timeout=self.timeout)
        except queue.Empty as error:
            raise TimeoutError("needle2_timeout") from error
        if line is None:
            raise RuntimeError("needle2_worker_closed")
        response = decode(line)
        if not isinstance(response, dict) or "worker_error" in response:
            raise RuntimeError("needle2_worker_failed")
        return response

    def _send(self, payload):
        # A stopped native worker can leave even initialization blocked on a
        # full pipe. Bound writes as well as reads, then terminate on timeout.
        # Preserve schema field order: the native engine is sensitive to it.
        # Canonical encoding is suitable for hashes, not for the model prompt.
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8") + b"\n"
        stream = self._process.stdin
        sent = queue.Queue()
        def write():
            try:
                stream.write(data)
                stream.flush()
                sent.put(None)
            except (OSError, ValueError) as error:
                sent.put(error)
        threading.Thread(target=write, daemon=True).start()
        try:
            error = sent.get(timeout=self.timeout)
        except queue.Empty as error:
            raise TimeoutError("needle2_timeout") from error
        if error is not None:
            raise error

    def _start(self, catalog):
        self._stop()
        started = time.perf_counter()
        self.library_sha256 = hashlib.sha256(self.library_path.read_bytes()).hexdigest()
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                   NEEDLE_TELEMETRY="0", DO_NOT_TRACK="1",
                   HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_OFFLINE="1")
        root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = root
        self._process = subprocess.Popen(
            [self.python_executable, "-m", "skills.tool_router.needle2_worker",
             "--library", str(self.library_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=root, env=env)
        self._messages = queue.Queue()
        threading.Thread(target=self._read_output,
                         args=(self._process, self._messages), daemon=True).start()
        self._send({"tools": catalog})
        ready = self._receive()
        if ready.get("ready") is not True:
            raise RuntimeError("needle2_initialization_failed")
        self.worker_runtime = {k: ready.get(k) for k in ("package_version", "python", "generation")}
        self._catalog = catalog
        self.startup_ms = (time.perf_counter() - started) * 1000

    def _stop(self):
        process, self._process = self._process, None
        self._catalog = None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                stream.close()

    def close(self):
        with self._lock:
            self._stop()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def route(self, query, tools):
        if not isinstance(query, str) or not query.strip():
            return ToolRouteResult.abstain("needle2", "empty_query")
        if len(query.encode("utf-8")) > MAX_QUERY_BYTES:
            return ToolRouteResult.abstain("needle2", "input_too_large")
        if not tools or len(tools) > MAX_TOOLS or len({t.name for t in tools}) != len(tools):
            return ToolRouteResult.abstain("needle2", "invalid_tool_catalog")
        catalog = [tool.as_dict() for tool in tools]
        if len(encode(catalog)) > 16_384:
            return ToolRouteResult.abstain("needle2", "tool_catalog_too_large")
        if self.library_path is None or not self.library_path.is_file():
            return ToolRouteResult.abstain("needle2", "needle2_library_missing")
        with self._lock:
            try:
                if self._process is None or self._catalog != catalog:
                    self._start(catalog)
                self._send({"query": query})
                response = self._receive()
            except TimeoutError:
                self._stop()
                return ToolRouteResult.abstain("needle2", "needle2_timeout")
            except (OSError, RuntimeError, ValueError, TypeError, RecursionError):
                self._stop()
                return ToolRouteResult.abstain("needle2", "needle2_runtime_error")
        return parse_response(response, tools, self.confidence_threshold)


def parse_response(response, tools, threshold=0.9):
    """Validate the actual Needle 2 response contract, not needle-rs output."""
    abstain = lambda reason: ToolRouteResult.abstain("needle2", reason)
    if not isinstance(response, dict) or response.get("success") is not True:
        return abstain("model_response_failed")
    if response.get("error") or response.get("error_code") or response.get("ungrounded"):
        return abstain("model_response_failed")
    validation = response.get("validation")
    if validation is not None and (not isinstance(validation, dict) or validation.get("ungrounded")):
        return abstain("ungrounded_arguments")
    if validation and validation.get("negation"):
        return abstain("negated_request")
    calls = response.get("function_calls")
    if calls == []:
        return abstain("model_abstained")
    if response.get("type") != "call" or not isinstance(calls, list) or len(calls) != 1:
        return abstain("single_call_required")
    confidence = response.get("confidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        return abstain("invalid_confidence")
    if confidence < threshold:
        return replace(abstain("low_confidence"), confidence=float(confidence))
    call = calls[0]
    if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
        return abstain("invalid_call")
    spec = next((tool for tool in tools if tool.name == call["name"]), None)
    if spec is None:
        return abstain("tool_not_allowed")
    try:
        validate(spec.parameters, call["arguments"])
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return abstain("invalid_arguments")
    result = validate_route(call["name"], call["arguments"], tools,
                            source="needle2", confidence=confidence)
    # The legacy router contract uses executable=True for schema conformance.
    # This pilot explicitly never grants execution authority.
    return replace(result, executable=False, reason=result.reason or "advisory_only")
