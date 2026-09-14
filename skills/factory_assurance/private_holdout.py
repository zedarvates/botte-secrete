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
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

from .adapters import holdout_attestation


class PrivateHoldoutError(RuntimeError):
    """Raised when the private holdout or evaluator protocol is invalid."""


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_private_set(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PrivateHoldoutError("private holdout must be a JSON object")
    set_id = str(value.get("set_id") or "").strip()
    cases = value.get("cases")
    if not set_id:
        raise PrivateHoldoutError("private holdout set_id is required")
    if not isinstance(cases, list) or not cases:
        raise PrivateHoldoutError("private holdout requires at least one case")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise PrivateHoldoutError(f"case {index} must be an object")
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            raise PrivateHoldoutError(f"case {index} id is required")
        if case_id in seen:
            raise PrivateHoldoutError(f"duplicate private case id: {case_id}")
        seen.add(case_id)
        if "input" not in case:
            raise PrivateHoldoutError(f"case {case_id} input is required")
    return value


def _subprocess_evaluator(argv: Sequence[str], case: dict[str, Any], timeout: float) -> bool:
    if not argv or any(not str(part) for part in argv):
        raise PrivateHoldoutError("evaluator argv must be non-empty")
    request = {"id": str(case["id"]), "input": case["input"]}
    try:
        completed = subprocess.run(
            [str(part) for part in argv],
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrivateHoldoutError(f"evaluator timed out for case {case['id']}") from exc
    if completed.returncode != 0:
        raise PrivateHoldoutError(
            f"evaluator returned non-zero for case {case['id']}: {completed.returncode}"
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PrivateHoldoutError(f"evaluator returned invalid JSON for case {case['id']}") from exc
    if not isinstance(response, dict) or not isinstance(response.get("passed"), bool):
        raise PrivateHoldoutError(f"evaluator response for case {case['id']} must contain boolean passed")
    return bool(response["passed"])


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
    private_set = load_private_set(private_set_path)
    if evaluator is None and evaluator_argv is None:
        raise PrivateHoldoutError("an evaluator is required")
    if evaluator is not None and evaluator_argv is not None:
        raise PrivateHoldoutError("choose evaluator or evaluator_argv, not both")

    all_passed = True
    for case in private_set["cases"]:
        passed = (
            bool(evaluator(case))
            if evaluator is not None
            else _subprocess_evaluator(evaluator_argv or (), case, timeout_seconds)
        )
        all_passed = all_passed and passed

    return holdout_attestation(
        set_id=str(private_set["set_id"]),
        digest=_canonical_digest(private_set),
        candidate_sha=candidate_sha,
        passed=all_passed,
        case_count=len(private_set["cases"]),
    )


def write_attestation(attestation: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(attestation, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
