"""Private/external holdout runner for Factory Assurance.

The private case payload stays outside the repository. The runner reads it from a
local path, sends one case at a time to an explicitly supplied evaluator command
via stdin, and emits only a public-safe attestation. It never shells out through
a command string and never prints case payloads.

Evaluator protocol (stdin/stdout JSON, one process per case):
  stdin:  {"id": <opaque id>, "input": <private payload>}
  stdout: {"passed": true|false}

The evaluator may perform target-specific validation. Its command is supplied as
an argv list by the operator; Factory Assurance does not discover or download
executables automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

from .adapters import _hex_digest, _strict_json, holdout_attestation


class PrivateHoldoutError(RuntimeError):
    """Raised when the private holdout or evaluator protocol is invalid."""


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_private_set(path: str | Path) -> dict[str, Any]:
    try:
        value = _strict_json(Path(path).read_text(encoding="utf-8"))
    except ValueError:
        raise PrivateHoldoutError("private holdout must contain unambiguous JSON") from None
    if not isinstance(value, dict):
        raise PrivateHoldoutError("private holdout must be a JSON object")
    set_id = value.get("set_id")
    cases = value.get("cases")
    if not isinstance(set_id, str) or not set_id.strip():
        raise PrivateHoldoutError("private holdout set_id is required")
    if not isinstance(cases, list) or not cases:
        raise PrivateHoldoutError("private holdout requires at least one case")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise PrivateHoldoutError(f"case {index} must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise PrivateHoldoutError(f"case {index} id is required")
        if case_id.strip() in seen:
            raise PrivateHoldoutError("duplicate private case id")
        seen.add(case_id.strip())
        if "input" not in case:
            raise PrivateHoldoutError(f"case {index} input is required")
    return value


def _subprocess_evaluator(argv: Sequence[str], case: dict[str, Any], timeout: float) -> bool:
    request = {"id": case["id"], "input": case["input"]}
    try:
        completed = subprocess.run(
            list(argv),
            input=json.dumps(request, ensure_ascii=False, allow_nan=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrivateHoldoutError("evaluator timed out") from exc
    if completed.returncode != 0:
        raise PrivateHoldoutError("evaluator returned non-zero")
    try:
        response = _strict_json(completed.stdout)
    except ValueError:
        raise PrivateHoldoutError("evaluator returned invalid JSON") from None
    if not isinstance(response, dict) or set(response) != {"passed"} or type(response["passed"]) is not bool:
        raise PrivateHoldoutError("evaluator response must contain only boolean passed")
    return response["passed"]


def run_private_holdout(
    *,
    private_set_path: str | Path,
    candidate_sha: str,
    evaluator_argv: Sequence[str] | None = None,
    evaluator: Callable[[dict[str, Any]], bool] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Run a private set and return only a public-safe attestation.

    `evaluator` exists for embedding/tests. Normal CLI use supplies
    `evaluator_argv`. Case payloads and per-case outcomes are intentionally not
    included in the returned attestation.
    """
    candidate_sha = _hex_digest(candidate_sha, 40, "candidate_sha")
    if type(timeout_seconds) not in (int, float):
        raise PrivateHoldoutError("timeout must be a finite positive number")
    try:
        timeout_seconds = float(timeout_seconds)
    except OverflowError:
        raise PrivateHoldoutError("timeout must be a finite positive number") from None
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise PrivateHoldoutError("timeout must be a finite positive number")
    if evaluator is None and evaluator_argv is None:
        raise PrivateHoldoutError("an evaluator is required")
    if evaluator is not None and evaluator_argv is not None:
        raise PrivateHoldoutError("choose evaluator or evaluator_argv, not both")
    if evaluator is not None and not callable(evaluator):
        raise PrivateHoldoutError("evaluator must be callable")
    if evaluator_argv is not None and (
        not isinstance(evaluator_argv, Sequence) or isinstance(evaluator_argv, (str, bytes))
        or not evaluator_argv or any(not isinstance(part, str) or not part or "\x00" in part for part in evaluator_argv)
    ):
        raise PrivateHoldoutError("evaluator argv must contain non-empty strings")

    private_set = load_private_set(private_set_path)
    digest = _canonical_digest(private_set)

    all_passed = True
    for case in private_set["cases"]:
        passed = (
            evaluator(case)
            if evaluator is not None
            else _subprocess_evaluator(evaluator_argv or (), case, timeout_seconds)
        )
        if type(passed) is not bool:
            raise PrivateHoldoutError("evaluator must return a boolean")
        all_passed = all_passed and passed

    return holdout_attestation(
        set_id=private_set["set_id"],
        digest=digest,
        candidate_sha=candidate_sha,
        passed=all_passed,
        case_count=len(private_set["cases"]),
    )


def write_attestation(attestation: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(attestation, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
