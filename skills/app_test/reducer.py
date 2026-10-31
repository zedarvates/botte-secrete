"""Reduce a JSON-list reproduction while preserving one explicit failure.

``reduce_reproduction(items, oracle, max_calls=64, max_seconds=10)`` calls
``oracle(candidate)`` with a fresh JSON snapshot. The oracle returns an object
whose ``status`` is ``failed``, ``passed``, ``inconclusive``, ``error`` or
``timeout``. A failed result must include a nonempty ``failure_fingerprint``.
Only that exact fingerprint can preserve the initial witness. Different failures,
exceptions and unavailable evidence never count as a successful reduction.

The module executes no command and does not interpret test code. Callers own the
oracle and its isolation. The elapsed-time limit is cooperative: it prevents new
calls and rejects late results, but cannot interrupt a blocking Python callback.
A process adapter must enforce its own hard per-call timeout. No global minimum
or stability across future executions follows from the recorded observations.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from typing import Callable


_STATUSES = {"failed", "passed", "inconclusive", "error", "timeout"}
_MAX_NODES = 20000
_MAX_DEPTH = 32
_MAX_FINGERPRINT_BYTES = 1024
_MAX_TRACE = 128


def _integer_limit(value: object, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _json_snapshot(items: object, max_items: int, max_input_bytes: int) -> tuple[list, str]:
    if not isinstance(items, list) or len(items) > max_items:
        raise ValueError("items must be a JSON list within max_items")
    nodes = 0
    text_chars = 0
    active: set[int] = set()

    def visit(value: object, depth: int) -> None:
        nonlocal nodes, text_chars
        nodes += 1
        if nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise ValueError("input JSON exceeds structural limits")
        if isinstance(value, str):
            text_chars += len(value)
            if text_chars > max_input_bytes:
                raise ValueError("input JSON exceeds max_input_bytes")
            return
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, int):
            # Portable bound across Python 3.10 and newer interpreters with
            # integer-string conversion limits; failure inputs are not bigints.
            if value.bit_length() > 3400:
                raise ValueError("input integer exceeds supported size")
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("input JSON must contain finite numbers")
            return
        if not isinstance(value, (dict, list)):
            raise ValueError("items must contain JSON values only")
        identity = id(value)
        if identity in active:
            raise ValueError("input JSON must not contain cycles")
        active.add(identity)
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ValueError("JSON object keys must be strings")
            for key, child in value.items():
                text_chars += len(key)
                if text_chars > max_input_bytes:
                    raise ValueError("input JSON exceeds max_input_bytes")
                visit(child, depth + 1)
        else:
            for child in value:
                visit(child, depth + 1)
        active.remove(identity)

    visit(items, 0)
    try:
        encoded = _encode(items)
        if len(encoded.encode("utf-8")) > max_input_bytes:
            raise ValueError("input JSON exceeds max_input_bytes")
        return json.loads(encoded), encoded
    except (TypeError, OverflowError, UnicodeError, RecursionError) as error:
        raise ValueError("items cannot be represented as bounded UTF-8 JSON") from error


def _encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def _digest(encoded: str) -> str:
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return len(value.encode("utf-8")) <= _MAX_FINGERPRINT_BYTES
    except UnicodeError:
        return False


def reduce_reproduction(items: list, oracle: Callable[[list], dict], *,
                        max_calls: int = 64, max_seconds: float = 10.0,
                        max_items: int = 512, max_input_bytes: int = 131072,
                        expected_fingerprint: str | None = None) -> dict:
    """Return a bounded, deterministic deletion reduction and its observations.

    The oracle must not mutate its candidate. Final success requires a fresh
    matching failure observation. With only one allowed call, the baseline can
    be observed, but final verification is unavailable and remains inconclusive.
    A completed search may establish observed one-deletion minimality only;
    unknown oracle outcomes prevent that claim. Values themselves are returned
    in ``reduced_items``; callers should handle private inputs accordingly.
    """
    max_calls = _integer_limit(max_calls, "max_calls", 512)
    max_items = _integer_limit(max_items, "max_items", 4096)
    max_input_bytes = _integer_limit(max_input_bytes, "max_input_bytes", 1048576)
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not 0 < max_seconds <= 300 or not math.isfinite(max_seconds)):
        raise ValueError("max_seconds must be finite and between 0 and 300")
    if not callable(oracle):
        raise ValueError("oracle must be callable")
    if expected_fingerprint is not None and not _fingerprint(expected_fingerprint):
        raise ValueError("expected_fingerprint must be nonempty bounded UTF-8 text")
    original, encoded = _json_snapshot(items, max_items, max_input_bytes)
    current = original
    started = time.monotonic()
    deadline = started + float(max_seconds)
    calls = 0
    trace: list[dict] = []
    outcomes = {status: 0 for status in sorted(_STATUSES)}
    target = expected_fingerprint
    stop_reason = "search_complete"
    final: dict | None = None
    uncertain_deletions = False
    observed_one_minimal = False

    def observe(candidate: list, phase: str, *, reserve_final: bool = True) -> dict | None:
        nonlocal calls, stop_reason
        limit = max_calls - 1 if reserve_final else max_calls
        # The initial observation can consume the only available call.
        if phase == "baseline":
            limit = max_calls
        if calls >= limit:
            stop_reason = "call_budget"
            return None
        if time.monotonic() >= deadline:
            stop_reason = "time_budget"
            return None
        supplied = _encode(candidate)
        candidate_copy = json.loads(supplied)
        calls += 1
        before = time.monotonic()
        try:
            raw = oracle(candidate_copy)
            if (not isinstance(raw, dict) or not isinstance(raw.get("status"), str)
                    or raw["status"] not in _STATUSES):
                observation = {"status": "inconclusive", "reason": "invalid_oracle_result"}
            elif raw["status"] == "failed" and not _fingerprint(raw.get("failure_fingerprint")):
                observation = {"status": "inconclusive", "reason": "missing_failure_fingerprint"}
            else:
                observation = {"status": raw["status"]}
                if raw["status"] == "failed":
                    observation["failure_fingerprint"] = raw["failure_fingerprint"]
            if _encode(candidate_copy) != supplied:
                observation = {"status": "error", "reason": "oracle_mutated_candidate"}
        except (TimeoutError, subprocess.TimeoutExpired):
            observation = {"status": "timeout", "reason": "oracle_timeout"}
        except Exception:
            # Error text may contain data, commands or credentials. Keep only a
            # stable category; the caller may retain detailed diagnostics.
            observation = {"status": "error", "reason": "oracle_exception"}
        ended = time.monotonic()
        if ended > deadline:
            observation = {"status": "timeout", "reason": "elapsed_deadline_exceeded"}
            stop_reason = "time_budget"
        outcomes[observation["status"]] += 1
        detail = {key: value for key, value in observation.items()
                  if key != "failure_fingerprint"}
        if "failure_fingerprint" in observation:
            detail["failure_fingerprint_sha256"] = _digest(observation["failure_fingerprint"])
        row = {"call": calls, "phase": phase, "candidate_count": len(candidate),
               "candidate_sha256": _digest(supplied), **detail,
               "duration_ms": round(max(0.0, ended - before) * 1000, 3)}
        trace.append(row)
        return observation

    def preserves(observation: dict | None) -> bool:
        return bool(observation and observation["status"] == "failed"
                    and observation.get("failure_fingerprint") == target)

    def report(status: str) -> dict:
        current_encoded = _encode(current)
        kept_trace = trace[:_MAX_TRACE]
        return {
            "schema": "parcimonia.reproduction-reduction/v1", "status": status,
            "stop_reason": stop_reason, "failure_fingerprint": target,
            "failure_preserved": preserves(final),
            "minimality": ("one_deletion_minimal_observed" if observed_one_minimal
                           and preserves(final) else "not_established"),
            "original_count": len(original), "reduced_count": len(current),
            "removed_count": len(original) - len(current), "reduced_items": current,
            "original_sha256": _digest(encoded), "reduced_sha256": _digest(current_encoded),
            "calls": calls, "outcomes": outcomes, "final_verification": final,
            "trace": kept_trace, "trace_omitted": max(0, len(trace) - len(kept_trace)),
            "limits": {"max_calls": max_calls, "max_seconds": float(max_seconds),
                       "max_items": max_items, "max_input_bytes": max_input_bytes},
            "boundaries": {"oracle": "caller_supplied", "oracle_isolation": "caller_owned",
                           "time_limit": "cooperative_callback", "global_minimum": False,
                           "future_stability": "not_established"},
        }

    baseline = observe(current, "baseline", reserve_final=False)
    if not baseline or baseline["status"] != "failed":
        if baseline and stop_reason not in ("call_budget", "time_budget"):
            stop_reason = "baseline_not_failed"
        return report("not_reproduced" if baseline and baseline["status"] == "passed"
                      else "inconclusive")
    if target is None:
        target = baseline["failure_fingerprint"]
    elif not preserves(baseline):
        stop_reason = "baseline_failure_mismatch"
        return report("not_reproduced")

    if current:
        empty = observe([], "empty")
        if preserves(empty):
            current = []
            stop_reason = "empty_failure"
            observed_one_minimal = True
    else:
        stop_reason = "empty_failure"
        observed_one_minimal = True

    n = 2
    while current and stop_reason not in ("call_budget", "time_budget"):
        n = min(n, len(current))
        accepted = False
        uncertain_deletions = False
        # Integer partition boundaries are stable and cover every item once.
        for part in range(n):
            start = part * len(current) // n
            end = (part + 1) * len(current) // n
            candidate = current[:start] + current[end:]
            observation = observe(candidate, "delete")
            if observation is None:
                break
            if observation["status"] in ("inconclusive", "error", "timeout"):
                uncertain_deletions = True
            if preserves(observation):
                current = candidate
                n = max(2, n - 1)
                accepted = True
                break
        if stop_reason in ("call_budget", "time_budget"):
            break
        if accepted:
            continue
        if n == len(current):
            observed_one_minimal = not uncertain_deletions
            break
        n = min(len(current), n * 2)

    search_reason = stop_reason
    final = observe(current, "final", reserve_final=False)
    if final is None:
        return report("inconclusive")
    if not preserves(final):
        if stop_reason not in ("call_budget", "time_budget"):
            stop_reason = "final_failure_not_preserved"
        return report("inconclusive")
    stop_reason = search_reason
    return report("reduced" if len(current) < len(original) else "unchanged")
