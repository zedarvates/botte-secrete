#!/usr/bin/env python3
"""Read-only worktree/result reconciliation; never delete or prune anything."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skills.completion_proof.verify import verify_report

SCHEMA = "botte.worktree-lifecycle/v1"
MAX_JSON = 1_000_000
MAX_GIT = 2_000_000
MAX_REPORT = 2_000_000
MAX_WORKTREES = 256
SHA = re.compile(r"[0-9a-f]{40}\Z")
STATUS_ARGS = ("status", "--porcelain=v1", "-z", "--untracked-files=all",
               "--ignored=matching", "--ignore-submodules=none")


class InspectionError(ValueError):
    pass


def _json(data: bytes) -> dict:
    if len(data) > MAX_JSON:
        raise InspectionError("manifest_too_large")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise InspectionError("duplicate_json_key")
            value[key] = item
        return value

    def constant(_value):
        raise InspectionError("nonfinite_json")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InspectionError("invalid_manifest") from exc
    if not isinstance(value, dict):
        raise InspectionError("manifest_must_be_object")
    return value


def _path(value) -> Path:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise InspectionError("invalid_path")
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise InspectionError("linked_path")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InspectionError("missing_path") from exc


def _git(root: Path, *args, success=(0,)) -> tuple[int, bytes]:
    # Disabling optional locks avoids index refresh; fsmonitor is never invoked.
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
               "-C", str(root), *args]
    try:
        with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as process:
            def read(stream):
                data = stream.read(MAX_GIT + 1)
                if len(data) > MAX_GIT:
                    process.kill()
                return data

            with ThreadPoolExecutor(max_workers=2) as pool:
                stdout = pool.submit(read, process.stdout)
                stderr = pool.submit(read, process.stderr)
                try:
                    code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
                output, errors = stdout.result(), stderr.result()
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise InspectionError("git_unavailable") from exc
    if len(output) > MAX_GIT or len(errors) > MAX_GIT:
        raise InspectionError("git_output_limit")
    if code not in success:
        raise InspectionError("git_inspection_failed")
    return code, output


def _commit(root: Path, ref: str) -> str:
    if (not isinstance(ref, str) or not ref or ref.startswith("-") or len(ref) > 256
            or any(ord(c) < 32 for c in ref)):
        raise InspectionError("invalid_revision")
    data = _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")[1]
    value = data.decode("ascii").strip()
    if not SHA.fullmatch(value):
        raise InspectionError("unsupported_git_object_format")
    return value


def _ancestor(root: Path, older: str, newer: str) -> bool:
    return _git(root, "merge-base", "--is-ancestor", older, newer, success=(0, 1))[0] == 0


def _inventory(root: Path) -> list[dict]:
    data = _git(root, "worktree", "list", "--porcelain", "-z")[1]
    entries, current = [], {}
    for token in data.split(b"\0"):
        if not token:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = token.partition(b" ")
        current[key.decode("ascii")] = value.decode("utf-8", errors="surrogateescape")
    if current:
        entries.append(current)
    return entries


def _proof(record: dict, path: Path, head: str) -> dict:
    proof = record.get("proof")
    if not isinstance(proof, dict) or proof.get("head_sha") != head:
        raise InspectionError("missing_or_unbound_result")
    evidence = _path(proof.get("evidence_root"))
    reference = proof.get("report")
    if (not isinstance(reference, str) or not reference or "\\" in reference
            or Path(reference).is_absolute() or ":" in reference
            or any(p in {"", ".", ".."} for p in reference.split("/"))):
        raise InspectionError("unsafe_report_reference")
    report = _path(str(evidence / reference))
    try:
        report.relative_to(evidence)
    except ValueError as exc:
        raise InspectionError("report_outside_root") from exc
    with report.open("rb") as stream:
        claim = _json(stream.read(MAX_JSON + 1))
    if claim.get("run_id") != record["task_id"]:
        raise InspectionError("task_result_mismatch")
    result = verify_report(report, evidence_root=evidence, source_root=path,
                           trusted_receipt_sha256=proof.get("trusted_receipt_sha256"))
    if result.get("verified") is not True or result.get("errors"):
        raise InspectionError("result_not_verified")
    return {"run_id": claim["run_id"], "report": reference,
            "receipt_sha256": result["receipt_sha256"],
            "scope": result["scope"]}


def inspect_worktrees(repository: str | Path, target: str, manifest: dict, *,
                      now: datetime | None = None) -> dict:
    """Reconcile current Git observations with explicit caller-owned records.

    Activity and provider PR state are declarations, not independently verified.
    Even a candidate is only a point-in-time proposal for owner review.
    """
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("records"), list):
        raise InspectionError("unsupported_manifest")
    records = manifest["records"]
    if len(records) > MAX_WORKTREES:
        raise InspectionError("too_many_records")
    root = _path(str(repository))
    main = _path(_git(root, "worktree", "list", "--porcelain", "-z")[1]
                 .split(b"\0", 1)[0].split(b" ", 1)[1].decode("utf-8"))
    target_sha = _commit(root, target)
    inventory = _inventory(root)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise InspectionError("timezone_required")
    by_path = {}
    for record in records:
        if not isinstance(record, dict):
            raise InspectionError("invalid_record")
        key = str(_path(record.get("path")))
        if key in by_path:
            raise InspectionError("duplicate_worktree_record")
        by_path[key] = record
    rows = []
    for entry in inventory[:MAX_WORKTREES]:
        row = {"path": entry.get("worktree"), "head_sha": entry.get("HEAD"),
               "status": "retain", "reasons": [], "evidence": None}
        try:
            path = _path(entry.get("worktree"))
            if path == main:
                raise InspectionError("primary_worktree")
            if "locked" in entry or "prunable" in entry or "bare" in entry:
                raise InspectionError("locked_or_unavailable_worktree")
            if "branch" not in entry:
                raise InspectionError("detached_head")
            head = _commit(path, "HEAD")
            row["head_sha"] = head
            before = _git(path, *STATUS_ARGS)[1]
            if before:
                raise InspectionError("dirty_untracked_or_ignored")
            record = by_path.get(str(path))
            if not record:
                raise InspectionError("missing_task_provenance")
            task = record.get("task_id")
            if not isinstance(task, str) or not task.strip() or len(task) > 128:
                raise InspectionError("invalid_task_id")
            row["task_id"] = task
            if record.get("task_state") != "accepted":
                raise InspectionError("task_not_accepted")
            if record.get("activity") != "idle":
                raise InspectionError("active_or_unknown_execution")
            try:
                observed = datetime.fromisoformat(record["activity_observed_at"].replace("Z", "+00:00"))
                age = (current_time - observed).total_seconds()
            except (KeyError, AttributeError, TypeError, ValueError) as exc:
                raise InspectionError("missing_activity_observation") from exc
            if not 0 <= age <= 300:
                raise InspectionError("stale_activity_observation")
            pr = record.get("pull_request")
            if not isinstance(pr, dict) or pr.get("state") != "merged":
                raise InspectionError("pull_request_not_merged")
            reference = pr.get("url")
            if not isinstance(reference, str) or len(reference) > 2048:
                raise InspectionError("invalid_pull_request_reference")
            url = urlparse(reference)
            if (url.scheme != "https" or url.netloc != "github.com" or url.query or url.fragment
                    or not re.fullmatch(r"/[^/]+/[^/]+/pull/[1-9][0-9]*", url.path)):
                raise InspectionError("invalid_pull_request_reference")
            if pr.get("head_sha") != head:
                raise InspectionError("pull_request_head_mismatch")
            merge_sha = pr.get("merge_sha")
            if not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha):
                raise InspectionError("missing_merge_revision")
            if not _ancestor(root, head, target_sha) or not _ancestor(root, merge_sha, target_sha):
                raise InspectionError("commits_not_integrated")
            row["evidence"] = _proof(record, path, head)
            if (_commit(path, "HEAD") != head or _commit(root, target) != target_sha
                    or _git(path, *STATUS_ARGS)[1]):
                raise InspectionError("changed_during_inspection")
            row.update(status="candidate_for_owner_review", reasons=["locally_integrated_clean_result"])
            row["pull_request"] = pr["url"]
        except (InspectionError, OSError, UnicodeError) as exc:
            row["reasons"].append(str(exc) if isinstance(exc, InspectionError) else "inspection_io_error")
        rows.append(row)
    omitted = max(0, len(inventory) - MAX_WORKTREES)
    declared_unmatched = sum(1 for key in by_path if key not in {str(Path(e["worktree"]).resolve()) for e in inventory})
    result = {"schema": SCHEMA, "mode": "read_only", "repository": str(root),
            "target_ref": target, "target_sha": target_sha,
            "observed_at": current_time.isoformat(), "worktrees": rows,
            "counts": {"observed": len(inventory), "returned": len(rows), "omitted": omitted,
                       "unmatched_records": declared_unmatched,
                       "candidates": sum(row["status"] == "candidate_for_owner_review" for row in rows)},
            "complete": omitted == 0,
            "limits": ["PR state and idle activity are caller declarations; no provider or process query",
                       "Only listed source files and recorded tests are verified",
                       "Squash/rebase heads not ancestral to target are retained",
                       "Snapshot only; repeat inspection before any separately authorized cleanup"],
            "mutations": [], "deletion_authorized": False}
    if len(json.dumps(result, ensure_ascii=True).encode("utf-8")) > MAX_REPORT:
        raise InspectionError("report_output_limit")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--target", required=True, help="Existing local integration ref, e.g. main")
    parser.add_argument("--records", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        with args.records.open("rb") as stream:
            manifest = _json(stream.read(MAX_JSON + 1))
        report = inspect_worktrees(args.repo, args.target, manifest)
    except (InspectionError, OSError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "error":
                          str(exc) if isinstance(exc, InspectionError) else "manifest_io_error"}))
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
