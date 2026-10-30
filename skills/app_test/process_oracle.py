"""Explicit local argv + JSON stdin/stdout adapter for trusted test commands.

No shell, model or implicit command discovery. A disposable process is not an
OS sandbox. This adapter adds per-call deadlines and bounded output reads; the
caller still supplies trusted code and its target environment.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time

from skills.app_test.prioritization import command_fingerprint


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path: str | Path, *, maximum: int = 131072):
    if not stat.S_ISREG(Path(path).stat().st_mode):
        raise ValueError("JSON input must be a regular file")
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("JSON input exceeds size limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def invoke_json(command: list[str], payload, *, cwd: str | Path | None = None,
                timeout_seconds: float = 5.0, max_output_bytes: int = 131072) -> dict:
    sha = command_fingerprint(command)
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 300 or not math.isfinite(timeout_seconds)):
        raise ValueError("timeout must be finite in (0,300]")
    if type(max_output_bytes) is not int or not 256 <= max_output_bytes <= 1048576:
        raise ValueError("output limit must be 256..1048576 bytes")
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded) > 131072:
        raise ValueError("oracle input exceeds size limit")
    started = time.monotonic()
    observation = {"command_sha256": sha}
    # Files avoid unbounded in-memory capture. The output cap is checked after
    # termination; this is not a filesystem quota for a misbehaving command.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                    stdout=out, stderr=err, shell=False,
                                    start_new_session=os.name == "posix")
        except OSError:
            return {**observation, "status": "not_run", "reason": "command_launch_failed"}
        try:
            proc.communicate(encoded, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.communicate()
            return {**observation, "status": "timeout", "reason": "process_deadline",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
        out.seek(0); raw = out.read(max_output_bytes + 1)
        err.seek(0); stderr = err.read(max_output_bytes + 1)
    observation.update(exit=proc.returncode,
                       elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                       stdout_sha256=hashlib.sha256(raw).hexdigest(),
                       stderr_prefix_sha256=hashlib.sha256(stderr).hexdigest())
    if len(raw) > max_output_bytes or len(stderr) > max_output_bytes:
        return {**observation, "status": "incomplete", "reason": "process_output_limit",
                "output_hash_covers": "bounded_prefix"}
    if proc.returncode != 0:
        return {**observation, "status": "error", "reason": "nonzero_process_exit"}
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if not isinstance(result, dict):
            raise ValueError("oracle output must be an object")
    except (UnicodeError, ValueError, RecursionError):
        return {**observation, "status": "incomplete", "reason": "invalid_json_result"}
    # Adapter provenance cannot be replaced by fields in the subject's output.
    return {**result, **observation}
