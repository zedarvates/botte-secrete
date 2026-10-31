"""Bounded observation of repeated test outcomes, without erasing failures.

``triage_failures(runner, seed=7, context={"build": commit})`` calls the supplied
adapter as ``runner(attempt_index, seed, context_sha256)``. The adapter returns
``status`` (passed/failed/incomplete/not_run), an optional failure_signature and
reason, and optionally its observed context_sha256. Context and seed are fixed
for the entire series. A changed context is retained but cannot support a
same-environment conclusion.

The module starts no subprocess, network request, model or thread itself. Its
time budget is cooperative: the adapter must enforce its own call timeout.
All classifications describe this finite observation, not general reliability
or the cause of an intermittent result.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from typing import Callable


_STATUSES = ("passed", "failed", "incomplete", "not_run")
_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_SIGNATURE_CHARS = 512
_MAX_REASON_CHARS = 1024


def _context_digest(context: dict | None) -> str:
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be a JSON object")
    try:
        encoded = json.dumps(context or {}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("context must be finite, UTF-8 JSON") from exc
    if len(encoded) > _MAX_CONTEXT_BYTES:
        raise ValueError("context exceeds 64 KiB")
    return hashlib.sha256(encoded).hexdigest()


def _normalize(value: object, expected_context: str) -> dict:
    if not isinstance(value, dict):
        return {"status": "incomplete", "reported_status": None,
                "reason": "invalid_adapter_result", "failure_signature": None,
                "context_match": None}
    reported = value.get("status")
    status = reported if isinstance(reported, str) and reported in _STATUSES else "incomplete"
    result = {"status": status,
              "reported_status": reported if reported in _STATUSES else None,
              "failure_signature": None,
              "context_match": None}
    reason = value.get("reason")
    if isinstance(reason, str):
        try:
            reason.encode("utf-8")
        except UnicodeError:
            result.update(status="incomplete", reason="invalid_reason_encoding")
        else:
            result["reason"] = reason[:_MAX_REASON_CHARS]
            if len(reason) > _MAX_REASON_CHARS:
                result["reason_truncated"] = True
    signature = value.get("failure_signature")
    if isinstance(signature, str) and signature:
        # Hash the complete signature before shortening its displayed form.
        try:
            signature_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        except UnicodeError:
            result.update(status="incomplete", reason="invalid_signature_encoding")
        else:
            result.update(failure_signature=signature[:_MAX_SIGNATURE_CHARS],
                          signature_sha256=signature_hash)
            if len(signature) > _MAX_SIGNATURE_CHARS:
                result["signature_truncated"] = True
    elif signature is not None:
        result.update(status="incomplete", reason="invalid_failure_signature")
    if reported not in _STATUSES:
        result.update(status="incomplete", reason="invalid_adapter_status")
    if "context_sha256" in value:
        observed = value["context_sha256"]
        matches = isinstance(observed, str) and observed == expected_context
        result["context_match"] = matches
        if not matches:
            # The original status/signature remain visible in this attempt.
            result.update(status="incomplete", reason="context_fingerprint_changed")
    return result


def _classification(attempts: list[dict]) -> str:
    if not attempts:
        return "insufficient_evidence"
    counts = Counter(a["status"] for a in attempts)
    if counts["not_run"] == len(attempts):
        return "environment_unavailable"
    if counts["passed"] and counts["failed"]:
        return "intermittent_observed"
    if counts["incomplete"] or counts["not_run"]:
        return "insufficient_evidence"
    if counts["passed"] == len(attempts):
        return "no_failure_observed"
    signatures = {a.get("signature_sha256") for a in attempts}
    if len(attempts) < 2 or None in signatures:
        return "insufficient_evidence"
    return "reproduced_failure" if len(signatures) == 1 else "varying_failures_observed"


def triage_failures(runner: Callable[[int, int, str], dict], *, seed: int = 0,
                    context: dict | None = None, max_attempts: int = 5,
                    max_seconds: float = 30.0,
                    clock: Callable[[], float] = time.monotonic) -> dict:
    """Retain a bounded fixed-seed series and classify only observed outcomes.

    Adapter exceptions become incomplete attempts, with exception type but no
    exception text. Failure signatures are caller supplied and not verified.
    The budget is checked before and after each synchronous adapter call; an
    overrun is explicit and does not pretend that the call was interrupted.
    """
    if not callable(runner) or not callable(clock):
        raise ValueError("runner and clock must be callable")
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be an integer in 0..4294967295")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 100:
        raise ValueError("max_attempts must be an integer in 1..100")
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not 0 <= max_seconds <= 300):
        raise ValueError("max_seconds must be finite in 0..300")
    digest = _context_digest(context)
    start = clock()
    last_observed = start
    attempts: list[dict] = []
    stop_reason = "attempt_budget"
    overrun = False
    for index in range(max_attempts):
        before = clock()
        last_observed = before
        if before - start >= max_seconds:
            stop_reason = "time_budget"
            break
        try:
            result = _normalize(runner(index, seed, digest), digest)
        except Exception as exc:
            result = {"status": "incomplete", "reported_status": None,
                      "failure_signature": None, "context_match": None,
                      "reason": "adapter_exception",
                      "error_type": type(exc).__name__[:64]}
        after = clock()
        last_observed = after
        attempts.append({"index": index, "seed": seed, "context_sha256": digest,
                         "elapsed_ms": round(max(0.0, after - before) * 1000, 3),
                         **result})
        if after - start >= max_seconds:
            stop_reason = "time_budget"
            overrun = after - start > max_seconds
            break
    counts = {status: sum(a["status"] == status for a in attempts) for status in _STATUSES}
    reported = {status: sum(a["reported_status"] == status for a in attempts)
                for status in _STATUSES}
    groups: dict[str, dict] = {}
    for attempt in attempts:
        if attempt["reported_status"] != "failed" or not attempt.get("signature_sha256"):
            continue
        key = attempt["signature_sha256"]
        group = groups.setdefault(key, {"signature_sha256": key,
                                       "failure_signature": attempt["failure_signature"],
                                       "attempt_indices": [], "eligible_attempt_indices": []})
        group["attempt_indices"].append(attempt["index"])
        if attempt["status"] == "failed":
            group["eligible_attempt_indices"].append(attempt["index"])
    return {"schema": "parcimonia.flaky-triage/v1",
            "classification": _classification(attempts),
            "seed": seed, "context_sha256": digest,
            "attempt_count": len(attempts),
            "elapsed_ms": round(max(0.0, last_observed - start) * 1000, 3),
            "attempts": attempts, "counts": counts, "reported_counts": reported,
            "failure_ever_reported": bool(reported["failed"]),
            "failure_groups": list(groups.values()),
            "stop_reason": stop_reason,
            "budget": {"max_attempts": max_attempts, "max_seconds": max_seconds,
                       "time_budget_kind": "cooperative_between_calls",
                       "observed_overrun": overrun},
            "boundaries": {"cause_diagnosed": False,
                           "general_reliability_established": False,
                           "adapter_data_verified": False,
                           "automatic_repair": False}}
