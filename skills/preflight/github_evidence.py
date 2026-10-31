"""Compact caller-supplied GitHub JSON without fetching or verifying it.

Input keys: repository, pull_request (objects in GitHub's REST shape), optional
observed_at, files (array), check_runs ({total_count, check_runs}), statuses
({state, statuses}) and completeness ({metadata, files, checks, statuses}, each
unknown/partial/complete). Unknown raw REST fields are ignored; unknown top-level
keys are rejected. Only GitHub HTTPS source URLs are retained; external or unsafe
detail URLs are omitted with a warning. Completeness is
caller-declared, never inferred from a successful-looking list.

The output is bounded to 12 KiB in compact JSON UTF-8. Byte measurements include
the whole output envelope. Subtract them at the caller; their difference may be
negative. They are not token,
latency, monetary or end-to-end measurements.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from skills.preflight.github_plan import _REPOSITORY

MAX_INPUT_BYTES = 131_072
MAX_OUTPUT_BYTES = 12_288
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")
_FAILED = {"failure", "timed_out", "cancelled", "action_required", "stale", "startup_failure", "error"}
_CHECK_STATUSES = {"queued", "in_progress", "completed", "waiting", "requested", "pending"}
_CHECK_CONCLUSIONS = {"success", "failure", "neutral", "cancelled", "skipped", "timed_out", "action_required", "stale", "startup_failure"}
_COMMIT_STATES = {"success", "failure", "pending", "error", "expected"}


def _count_label(value, known):
    return "unknown" if value is None else value if value in known else "other"


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value, label, minimum=0):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                              or not minimum <= value <= 9_007_199_254_740_991):
        raise ValueError(f"{label} must be a safe integer")
    return value


def _text(value, label, limit=256, truncate=False):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} contains invalid Unicode") from exc
    if len(encoded) > limit:
        if not truncate:
            raise ValueError(f"{label} is too long")
        return encoded[:limit].decode("utf-8", errors="ignore")
    return value


def _sha(value):
    if value is not None and (not isinstance(value, str) or not _SHA.fullmatch(value)):
        raise ValueError("commit SHA must contain 40 hexadecimal characters")
    return value.lower() if value else None


def _url(value):
    if value is None:
        return None
    value = _text(value, "GitHub source URL", 1024)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc not in {"github.com", "api.github.com"}
            or parsed.username or parsed.password or "?" in value or "#" in value
            or not parsed.path.startswith("/") or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError("source URLs must be GitHub HTTPS URLs without credentials or query strings")
    return value


def _timestamp(value):
    if value is not None and (not isinstance(value, str) or not _DATE.fullmatch(value)):
        raise ValueError("timestamp must have an RFC3339 timezone")
    if value is not None:
        try:
            datetime(int(value[:4]), int(value[5:7]), int(value[8:10]),
                     int(value[11:13]), int(value[14:16]), int(value[17:19]))
        except ValueError as exc:
            raise ValueError("timestamp has an invalid calendar date or time") from exc
        if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
            raise ValueError("timestamp has an invalid timezone offset")
    return value


def _detail_url(value, warnings):
    if value is not None and not isinstance(value, str):
        raise ValueError("detail URL must be a string or null")
    try:
        return _url(value)
    except ValueError:
        warning = "non_github_or_unsafe_detail_url_omitted"
        if warning not in warnings:
            warnings.append(warning)
        return None


def _list(value, label):
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError(f"{label} must be an array of at most 1000 objects")
    return [_object(item, label) for item in value]


def _measure(result):
    measures = result["measurements"]
    for _ in range(8):
        size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if measures["output_utf8_bytes"] == size:
            return size
        measures["output_utf8_bytes"] = size
    raise ValueError("byte measurement did not converge")


def summarize_github_evidence(report_json: str) -> dict:
    """Select bounded review fields; never declare a review or merge safe."""
    if not isinstance(report_json, str):
        raise ValueError("report_json must be a string")
    try:
        input_bytes = len(report_json.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("report_json contains invalid Unicode") from exc
    if input_bytes > MAX_INPUT_BYTES:
        raise ValueError("report_json exceeds 128 KiB")
    try:
        report = json.loads(report_json, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON number")))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("report_json is invalid JSON") from exc
    _object(report, "report")
    allowed = {"repository", "observed_at", "pull_request", "files", "check_runs", "statuses", "completeness"}
    if set(report) - allowed:
        raise ValueError("unsupported report fields")
    stack = [(report, 0)]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if depth > 12 or visited > 12_000:
            raise ValueError("report structure is too deep or large")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    repository = report.get("repository")
    if (not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
            or repository.split("/", 1)[1] in {".", ".."}):
        raise ValueError("repository must be owner/repo")
    pr = _object(report.get("pull_request"), "pull_request")
    number = _integer(pr.get("number"), "PR number", 1)
    if number is None:
        raise ValueError("pull_request.number is required")
    head = _object(pr.get("head", {}), "head")
    base = _object(pr.get("base", {}), "base")
    head_sha = _sha(head.get("sha"))
    base_sha = _sha(base.get("sha"))
    base_repo = _object(base.get("repo", {}), "base.repo").get("full_name")
    if base_repo is not None and (not isinstance(base_repo, str) or not _REPOSITORY.fullmatch(base_repo)):
        raise ValueError("base repository must be owner/repo")
    for key in ("draft", "merged"):
        if pr.get(key) is not None and not isinstance(pr[key], bool):
            raise ValueError(f"{key} must be boolean or null")
    state = pr.get("state")
    if state is not None and (not isinstance(state, str) or state not in {"open", "closed"}):
        raise ValueError("PR state must be open, closed or null")
    source_url = _url(pr.get("html_url"))
    if source_url is not None and source_url != f"https://github.com/{repository}/pull/{number}":
        raise ValueError("PR URL must match the explicit repository and number")
    title = _text(pr.get("title"), "title", 256, truncate=True)
    completeness = _object(report.get("completeness", {}), "completeness")
    if set(completeness) - {"metadata", "files", "checks", "statuses"}:
        raise ValueError("unsupported completeness fields")
    completeness = {key: completeness.get(key, "unknown") for key in ("metadata", "files", "checks", "statuses")}
    if any(not isinstance(value, str) or value not in {"unknown", "partial", "complete"} for value in completeness.values()):
        raise ValueError("completeness must be unknown, partial or complete")
    files_raw = _list(report.get("files", []), "files")
    files = [{"filename": _text(f.get("filename"), "filename", 2048),
              "status": _text(f.get("status"), "file status", 32),
              "additions": _integer(f.get("additions"), "additions"),
              "deletions": _integer(f.get("deletions"), "deletions")} for f in files_raw]
    envelope = _object(report.get("check_runs", {}), "check_runs")
    checks_raw = _list(envelope.get("check_runs", []), "check_runs.check_runs")
    total = _integer(envelope.get("total_count"), "check_runs.total_count")
    checks, counts, revisions, warnings = [], Counter(), Counter(), []
    for item in checks_raw:
        status = _text(item.get("status"), "check status", 32)
        conclusion = _text(item.get("conclusion"), "check conclusion", 32)
        sha = _sha(item.get("head_sha"))
        match = "unknown" if not sha or not head_sha else "match" if sha == head_sha else "mismatch"
        counts[f"{_count_label(status, _CHECK_STATUSES)}:{_count_label(conclusion, _CHECK_CONCLUSIONS)}"] += 1
        revisions[match] += 1
        name = _text(item.get("name"), "check name", 160, truncate=True)
        checks.append({"name": name, "name_truncated": name != item.get("name"),
                       "status": status, "conclusion": conclusion, "head_sha": sha,
                       "revision_match": match, "details_url": _detail_url(item.get("details_url"), warnings)})
    checks.sort(key=lambda c: (0 if c["revision_match"] == "mismatch" or c["conclusion"] in _FAILED else 1 if c["status"] != "completed" else 2,
                               c["name"] or "", c["details_url"] or ""))
    status_envelope = _object(report.get("statuses", {}), "statuses")
    status_sha = _sha(status_envelope.get("sha"))
    status_revision = "unknown" if not status_sha or not head_sha else "match" if status_sha == head_sha else "mismatch"
    statuses_raw = _list(status_envelope.get("statuses", []), "statuses.statuses")
    statuses, status_counts = [], Counter()
    for item in statuses_raw:
        status = _text(item.get("state"), "commit status", 32)
        status_counts[_count_label(status, _COMMIT_STATES)] += 1
        context = _text(item.get("context"), "status context", 160, truncate=True)
        statuses.append({"context": context, "context_truncated": context != item.get("context"),
                         "state": status, "target_url": _detail_url(item.get("target_url"), warnings)})
    statuses.sort(key=lambda s: (0 if s["state"] in _FAILED else 1 if s["state"] != "success" else 2, s["context"] or ""))
    result = {
        "schema": "parcimonia.github-evidence-summary/v1",
        "source": {"kind": "caller_supplied", "verified": False, "repository": repository,
                   "observed_at": _timestamp(report.get("observed_at")), "url": source_url},
        "pull_request": {"number": number, "title": title, "title_truncated": title != pr.get("title"),
                         "state": state, "draft": pr.get("draft"), "merged": pr.get("merged"),
                         "merged_at": _timestamp(pr.get("merged_at")), "head_sha": head_sha,
                         "base_sha": base_sha, "base_ref": _text(base.get("ref"), "base.ref", 256),
                         "base_repository": base_repo},
        "completeness": completeness,
        "files": {"provided": "files" in report, "received": len(files), "selected": files[:6], "omitted": max(0, len(files) - 6)},
        "checks": {"provided": "check_runs" in report, "declared_total": total, "received": len(checks),
                   "list_incomplete": total is not None and total > len(checks),
                   "counts": dict(sorted(counts.items())), "revision_counts": dict(sorted(revisions.items())),
                   "selected": checks[:8], "omitted": max(0, len(checks) - 8)},
        "statuses": {"provided": "statuses" in report, "reported_state": _text(status_envelope.get("state"), "combined status", 32),
                     "received": len(statuses), "counts": dict(sorted(status_counts.items())),
                     "selected": statuses[:6], "omitted": max(0, len(statuses) - 6),
                     "head_sha": status_sha, "revision_match": status_revision},
        "warnings": warnings,
        "boundaries": {"execution": False, "network_calls": 0, "model_calls": 0, "merge_eligibility": "not_assessed"},
        "measurements": {"serialization": "compact-json-utf8", "input_utf8_bytes": input_bytes,
                         "output_utf8_bytes": 0, "host_tokens": None,
                         "cost": None, "latency_ms": None},
    }
    if revisions["mismatch"]:
        result["warnings"].append("check_head_mismatch")
    if total is not None and total != len(checks):
        result["warnings"].append("check_total_differs_from_received")
    if pr.get("merged") is False and pr.get("merged_at") is not None:
        result["warnings"].append("inconsistent_merge_metadata")
    if "statuses" in report and status_revision == "unknown":
        result["warnings"].append("status_revision_not_bound_by_supplied_envelope")
    if status_revision == "mismatch":
        result["warnings"].append("status_head_mismatch")
    while _measure(result) > MAX_OUTPUT_BYTES:
        section = max((result[key] for key in ("files", "checks", "statuses")), key=lambda s: len(s["selected"]))
        if not section["selected"]:
            raise ValueError("summary metadata exceeds output budget")
        section["selected"].pop()
        section["omitted"] += 1
    return result
