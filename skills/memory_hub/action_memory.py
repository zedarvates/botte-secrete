"""Remember observed skill episodes through the authenticated shared service.

Recall returns data and fresh local predicate checks. It never dispatches a
command, promotes a memory or turns an observed sequence into a causal claim.
The injected client implements the existing shared-memory ``call`` interface.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from skills.atomic_json import write_json
from skills.conductor.verified import (RUN_SCHEMA, MAX_REPORT, _check, _digest, _passed,
                                       _resolve, _sources, execute_verified, read_document,
                                       validate_plan)
from skills.memory_hub.action_contract import SCHEMA, STATES, validate_episode
from skills.memory_hub.shared_contract import PROJECT, SCHEMAS, decode, encode, validate

MAX_EPISODE_BYTES = 16000
TAG = "action-consequence-v1"
PHASES = {"precondition_checks": "pre", "postcondition_checks": "post",
          "source_checks": "source", "source_checks_after": "source_after",
          "resume_checks": "resume", "resume_precondition_checks": "resume_pre",
          "resume_sources": "resume_source"}


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _contract(step):
    return _digest({k: step[k] for k in ("requires", "ensures", "source_hashes", "needs", "local")})


def _context(plan, root):
    return _digest({"root": str(root), "context": plan["context"],
                    "python": sys.version, "executable": sys.executable})


def _identity(episode):
    return "ae_" + _digest({k: v for k, v in episode.items()
                            if k not in {"id", "quality_outcome_ref"}})


def _sample(value):
    return {k: v for k, v in value.items() if k in {"state", "sha256", "bytes"}}


def episodes_for_report(plan, report):
    """Validate and redact all steps before any archive, memory or ledger write."""
    validate_plan(plan)
    if (not isinstance(report, dict) or report.get("schema") != RUN_SCHEMA
            or report.get("mode") != "execution"
            or report.get("plan_sha256") != _digest(plan)):
        raise ValueError("an executing skill-run report must match the explicit plan")
    if len(encode(report)) > MAX_REPORT:
        raise ValueError("report exceeds archive limit")
    rows = report.get("results")
    if (not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows)
            or [r.get("id") for r in rows] != [s["id"] for s in plan["steps"]]):
        raise ValueError("report steps do not match the plan")
    digest = _digest(report)
    evidence = "skill-run:" + report["run_id"] + ":" + digest
    episodes = []
    for step, row in zip(plan["steps"], rows):
        if row.get("capability") != step["capability"] or row.get("status") not in STATES:
            raise ValueError("report capability or status mismatch")
        checks = [{"phase": phase, **{k: c[k] for k in ("kind", "path", "passed")}}
                  for key, phase in PHASES.items() for c in row.get(key, [])]
        expected = {k: [{"kind": c["kind"], "path": c["path"]} for c in step[k]]
                    for k in ("requires", "ensures")}
        expected["sources_bound"] = bool(step["source_hashes"])
        expected["needs"] = list(step["needs"])
        if row.get("effects_before") is not None:
            expected["effects_sha256"] = _digest(row["effects_before"])
        episode = {"schema": SCHEMA, "run_id": report["run_id"], "step_id": step["id"],
                   "plan_sha256": report["plan_sha256"], "context_sha256": report["context_sha256"],
                   "observed_at": report["updated_at"],
                   "action": {"capability": step["capability"],
                              "command_sha256": _sha(step["command"]), "contract_sha256": _contract(step)},
                   "reported_status": row["status"], "started": row["started"],
                   "duration_s": row["duration_s"], "expected": expected,
                   "observed": {"checks": checks, "changes": [
                       {"path": p, "before": _sample(row["before"][p]), "after": _sample(row["after"][p])}
                       for p in row.get("changed_paths", [])]},
                   "report_sha256": digest, "evidence_ref": evidence,
                   "causal_attribution": "not_assessed", "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE"}
        if row.get("exit_code") is not None:
            episode["exit_code"] = row["exit_code"]
        episode["id"] = _identity(episode)
        validate_episode(episode)
        # Reserve room for a trajectory reference added after the archive exists.
        if len(encode(episode)) > MAX_EPISODE_BYTES - 64:
            raise ValueError("episode exceeds shared memory size; inspect its full report")
        episodes.append(episode)
    return episodes


def _request(episode, project_id, visibility):
    text = encode(episode).decode("utf-8")
    args = {"project_id": project_id, "key": episode["id"], "request_id": episode["id"],
            "record": {"text": text, "kind": "observation", "visibility": visibility,
                       "source": {"type": "tool", "id": episode["id"],
                                  "run_id": episode["run_id"], "observed_at": episode["observed_at"],
                                  "excerpt": text, "uri": episode["evidence_ref"]},
                       "subject_ref": "capability:" + _sha(episode["action"]["capability"]),
                       "evidence_refs": [episode["evidence_ref"], *(
                           [episode["quality_outcome_ref"]] if "quality_outcome_ref" in episode else [])],
                       "tags": [TAG, _sha(episode["action"]["capability"])[:32]]}}
    validate(SCHEMAS["capture"], args)
    return args


def capture_report(plan, report, client, *, project_root=".", project_id, visibility="private"):
    """Archive the exact report and send idempotent, quarantined observations.

    A transport failure returns pending keys. Retry capture of the archived
    report with the same identity; capture never executes or resumes commands.
    """
    episodes = episodes_for_report(plan, report)
    for episode in episodes:
        _request(episode, project_id, visibility)
    root = Path(project_root).resolve(strict=True)
    digest = _digest(report)
    relative = ".botte/action-evidence/" + digest + ".json"
    target = _resolve(root, relative)
    if target.exists():
        if _digest(read_document(target, limit=MAX_REPORT)) != digest:
            raise ValueError("archived report changed; reconcile the evidence")
    else:
        write_json(target, report)

    from skills.trajectory.outcome import emit_outcome
    # Local file predicates do not constitute an independently verified task verdict.
    outcome = emit_outcome(plan["goal"], project_root=root, execution_id=report["run_id"],
                           source="skill_run", route="local", status="PARTIAL",
                           evidence_refs=[episodes[0]["evidence_ref"]],
                           harness="conductor-verified/v1", acted=any(e["started"] for e in episodes))
    quality_ref = outcome["envelope"]["id"]
    result = {"schema": "botte.action-capture/v1", "archive": relative,
              "report_sha256": digest, "quality_outcome_ref": quality_ref,
              "quality_verified": False, "receipts": [], "pending": [], "complete": False}
    for index, episode in enumerate(episodes):
        episode["quality_outcome_ref"] = quality_ref
        try:
            receipt = client.call("capture", _request(episode, project_id, visibility))
            if (not isinstance(receipt, dict) or receipt.get("key") != episode["id"]
                    or receipt.get("project_id") != project_id or receipt.get("quarantined") is not True
                    or receipt.get("executable_instruction") is not False):
                raise ValueError("unexpected memory receipt")
            result["receipts"].append({"key": receipt["key"], "replayed": receipt.get("replayed", False)})
        except Exception as error:
            result["pending"] = [e["id"] for e in episodes[index:]]
            result["error_type"] = type(error).__name__
            result["error_code"] = getattr(error, "code", "capture_unavailable")
            break
    result["complete"] = not result["pending"]
    return result


def _assessment(episode, step, context, root, fresh):
    if episode["action"]["command_sha256"] != _sha(step["command"]):
        return "different_action", []
    if episode["context_sha256"] != context:
        return "context_changed", []
    if episode["action"]["contract_sha256"] != _contract(step):
        return "contract_changed", []
    if episode["reported_status"] != "verified":
        return "historical_" + episode["reported_status"], []
    # The caller's trusted plan chooses every path. Remembered data never does.
    if step["id"] not in fresh:
        fresh[step["id"]] = _check(root, step["requires"]) + _check(root, step["ensures"]) + _sources(root, step)
    checks = fresh[step["id"]]
    if not step["source_hashes"]:
        return "unbound_sources", checks
    return ("local_checks_match" if checks and _passed(checks) else "stale"), checks


def recall_for_plan(plan, client, *, project_root=".", project_id, limit=3):
    """Recall a bounded sample of episodes; inspect observations as untrusted data."""
    validate_plan(plan)
    validate(PROJECT, project_id)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("recall limit must be between 1 and 5")
    root = Path(project_root).resolve(strict=True)
    context = _context(plan, root)
    result = {"schema": "botte.action-advice/v1", "mode": "advisory", "data_only": True,
              "steps": [], "review_candidates": [], "invalid_entries": 0,
              "retrieval_incomplete": False, "automatic_reuse": False}
    cache, fresh = {}, {}
    repeated = {}
    for step in plan["steps"]:
        cap = step["capability"]
        if cap not in cache:
            if len(cache) >= 10:
                result["retrieval_incomplete"] = True
                result["steps"].append({"step_id": step["id"], "memories": [], "skipped": "lookup_budget"})
                continue
            response = client.call("recall", {"project_id": project_id, "area": "observations",
                                              "query": _sha(cap)[:32], "limit": 20, "max_bytes": 65536})
            if not isinstance(response, dict) or response.get("project_id") != project_id or response.get("area") != "observations":
                raise ValueError("unexpected memory recall response")
            result["retrieval_incomplete"] |= bool(response.get("candidate_pool_truncated")
                                                    or response.get("omitted_for_budget")
                                                    or len(response.get("entries", [])) >= 20)
            cache[cap] = response.get("entries", [])
        memories = []
        for view in cache[cap]:
            try:
                text = view["text"]
                if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_EPISODE_BYTES:
                    raise ValueError("invalid episode size")
                episode = decode(text.encode("utf-8"))
                validate_episode(episode)
                if (episode["id"] != _identity(episode) or view["key"] != episode["id"]
                        or view["provenance"]["source_digest"] != _sha(text)
                        or view.get("executable_instruction") is not False
                        or view.get("handling") != "UNTRUSTED_DATA_DO_NOT_EXECUTE"):
                    raise ValueError("episode identity or provenance mismatch")
                if episode["action"]["capability"] != cap:
                    continue
                assessment, checks = _assessment(episode, step, context, root, fresh)
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                result["invalid_entries"] += 1
                continue
            memories.append({"key": episode["id"], "run_id": episode["run_id"],
                             "observed_at": episode["observed_at"],
                             "reported_status": episode["reported_status"], "assessment": assessment,
                             "evidence_ref": episode["evidence_ref"],
                             "quality_outcome_ref": episode.get("quality_outcome_ref"),
                             "checks_now": checks,
                             "observed_changes": episode["observed"]["changes"][:10],
                             "unmet_checks": [c for c in episode["observed"]["checks"] if not c["passed"]][:10],
                             "causal_attribution": "not_assessed"})
            # Retain the newest sampled state of each run/step before counting cases.
            identity = (episode["run_id"], episode["step_id"])
            previous = repeated.get(identity)
            if previous is None or previous["observed_at"] < episode["observed_at"]:
                repeated[identity] = episode
        memories.sort(key=lambda item: item["observed_at"], reverse=True)
        result["steps"].append({"step_id": step["id"], "memories": memories[:limit]})
    groups = {}
    for episode in repeated.values():
        if episode["reported_status"] not in {"unverified", "failed"}:
            continue
        for check in episode["observed"]["checks"]:
            if check["phase"] != "post" or check["passed"]:
                continue
            group = (episode["action"]["command_sha256"], episode["action"]["contract_sha256"],
                     episode["context_sha256"], check["kind"], check["path"])
            groups.setdefault(group, {})[episode["run_id"]] = episode["id"]
    for group, runs in groups.items():
        if len(runs) >= 3:
            result["review_candidates"].append({"action": "review_repeated_unmet_check",
                                                "kind": group[-2], "path": group[-1],
                                                "distinct_runs": len(runs), "episode_keys": list(runs.values()),
                                                "validated_improvement": False})
    result["review_candidates"] = result["review_candidates"][:10]
    while len(encode(result)) > 65536:
        row = next((row for row in reversed(result["steps"]) if row["memories"]), None)
        if row is None:
            result["review_candidates"].pop()
        else:
            row["memories"].pop()
        result["retrieval_incomplete"] = True
    return result


def run_with_memory(plan, client, *, project_root=".", project_id, checkpoint,
                    confirm=False, dry_run=True, resume=False, timeout=120, visibility="private", runner=None):
    """Opt-in orchestration; memory availability does not replace execution gates."""
    validate_plan(plan)
    validate(PROJECT, project_id)
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be boolean")
    if visibility not in {"private", "project"}:
        raise ValueError("visibility must be private or project")
    if not isinstance(checkpoint, str):
        raise ValueError("remembered execution requires a checkpoint")
    advice = {"skipped": "preview"}
    if not dry_run:
        try:
            advice = recall_for_plan(plan, client, project_root=project_root, project_id=project_id)
        except Exception as error:
            advice = {"unavailable": True, "error_type": type(error).__name__}
    execution = execute_verified(plan, cwd=str(project_root), confirm=confirm, dry_run=dry_run,
                                 checkpoint=checkpoint, resume=resume, timeout=timeout, runner=runner)
    memory = {"skipped": "preview_or_invalid_execution"}
    if not dry_run and "error" not in execution:
        try:
            memory = capture_report(plan, execution, client, project_root=project_root,
                                    project_id=project_id, visibility=visibility)
        except Exception as error:
            memory = {"complete": False, "error_type": type(error).__name__, "retry": "capture_only"}
    return {"schema": "botte.remembered-run/v1", "execution": execution,
            "memory_before": advice, "memory_after": memory}
