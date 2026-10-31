"""Order all selected checks using bounded observed history, never skip them.

The score is a scheduling heuristic, not a predicted probability or measured
saving. Command identity matters: history from another command is not reused.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone


MAX_HISTORY = 5000


def command_fingerprint(command: list[str]) -> str:
    if not isinstance(command, list) or not command or not all(
            isinstance(x, str) and x and "\x00" not in x for x in command):
        raise ValueError("command must be a nonempty string array")
    raw = json.dumps(command, ensure_ascii=True, separators=(",", ":"))
    if len(raw) > 32768:
        raise ValueError("command exceeds size limit")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_history(history: object) -> list[dict]:
    if (not isinstance(history, dict)
            or history.get("schema") != "parcimonia.test-history/v1"
            or not isinstance(history.get("runs"), list)
            or len(history["runs"]) > MAX_HISTORY):
        raise ValueError("invalid bounded test history")
    omitted = history.get("omitted_older_observations", 0)
    if isinstance(omitted, bool) or not isinstance(omitted, int) or not 0 <= omitted <= 10**12:
        raise ValueError("invalid omitted observation count")
    rows = []
    for row in history["runs"]:
        if not isinstance(row, dict):
            raise ValueError("invalid history row")
        label, sha, duration = row.get("label"), row.get("command_sha256"), row.get("duration_ms")
        if (not isinstance(label, str) or not label or len(label) > 256
                or not isinstance(sha, str) or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or isinstance(duration, bool) or not isinstance(duration, (float, int))
                or not 0 <= duration <= 86400000 or not math.isfinite(duration)
                or row.get("outcome") not in ("passed", "failed", "incomplete")):
            raise ValueError("invalid history observation")
        rows.append({"label": label, "command_sha256": sha,
                     "duration_ms": float(duration), "outcome": row["outcome"]})
    return rows


def prioritize_checks(checks: list[tuple[str, list[str]]], history: object) -> dict:
    """Return every input once, ordered by observed failures/time then exploration.

    Previously failing commands come first, unseen commands retain their order,
    then previously passing commands run shortest first. Incomplete observations
    do not establish a success/failure rate. All required checks remain selected.
    """
    if not isinstance(checks, list) or len(checks) > 512:
        raise ValueError("at most 512 checks are supported")
    rows = validate_history(history)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row["outcome"] != "incomplete":
            grouped.setdefault((row["label"], row["command_sha256"]), []).append(row)
    labels = set()
    ranked = []
    for index, pair in enumerate(checks):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("each check needs a label and command")
        label, command = pair
        if not isinstance(label, str) or not label or len(label) > 256 or label in labels:
            raise ValueError("check labels must be unique nonempty strings")
        labels.add(label)
        sha = command_fingerprint(command)
        observed = grouped.get((label, sha), [])
        failed = sum(r["outcome"] == "failed" for r in observed)
        median = statistics.median(r["duration_ms"] for r in observed) if observed else None
        score = failed / len(observed) / max(median, 1.0) if observed else None
        if failed:
            key = (0, -score, index)
        elif not observed:
            key = (1, 0, index)
        else:
            key = (2, median, index)
        ranked.append((key, {"label": label, "command_sha256": sha,
                             "observations": len(observed), "observed_failures": failed,
                             "median_duration_ms": median, "heuristic_score": score,
                             "original_index": index}))
    ordered = [row for _, row in sorted(ranked, key=lambda r: r[0])]
    return {"schema": "parcimonia.test-order/v1", "status": "proposed",
            "policy": "observed_failure_rate_per_ms_then_unseen_then_shortest_passing",
            "selected_count": len(checks), "ordered": ordered, "omitted": 0,
            "boundaries": {"execution": False, "skips_required_checks": False,
                           "measured_savings": None}}


def append_observations(history: object, observations: list[dict]) -> dict:
    """Keep the newest bounded observations. No outcome replaces an earlier one."""
    previous = validate_history(history)
    added = validate_history({"schema": "parcimonia.test-history/v1", "runs": observations})
    all_rows = previous + added
    return {"schema": "parcimonia.test-history/v1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "runs": all_rows[-MAX_HISTORY:],
            "omitted_older_observations": history.get("omitted_older_observations", 0)
            + max(0, len(all_rows) - MAX_HISTORY)}
