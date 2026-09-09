"""Explicit local inference runs, paired benchmarks and replay-safe memory outbox."""
from __future__ import annotations

import statistics
import time
import uuid
from pathlib import Path

from skills.atomic_json import write_json
from skills.llm_backends.runtime_contract import (
    digest, load, plan, validate_config, validate_tasks,
)
from skills.llm_backends.runtime_io import (
    RuntimeFailure, check_context, infer, memory_client, messages_for,
    prepare_context, secret, verify,
)
from skills.memory_hub.shared_contract import SCHEMAS, encode, validate


def _summary(observations):
    result = {}
    for profile_id in sorted({o["requested_profile"] for o in observations}):
        rows = [o for o in observations if o["requested_profile"] == profile_id]
        result[profile_id] = {
            "count": len(rows), "completed": sum(o["status"] == "completed" for o in rows),
            "predicate_passes": sum(o["verified"] is True for o in rows),
            "fallbacks": sum(len(o["attempts"]) > 1 for o in rows),
            # Failures remain in latency statistics; they cannot win the comparison.
            "median_response_chain_ms": round(statistics.median(o["response_chain_ms"] for o in rows), 3),
        }
    return result


def compare(report):
    """Advisory comparison of the paired trials produced in one frozen run."""
    if report.get("schema") != "botte.runtime-run/v1" or report.get("kind") != "benchmark":
        raise ValueError("Comparison requires a runtime benchmark report")
    baseline = report["profile_order"][0]
    baseline_rows = [o for o in report["observations"] if o["requested_profile"] == baseline]
    comparisons = []
    for profile_id in report["profile_order"][1:]:
        rows = [o for o in report["observations"] if o["requested_profile"] == profile_id]
        key = lambda o: (o["task_id"], o["repeat"], o["messages_sha256"])
        paired = sorted(map(key, rows)) == sorted(map(key, baseline_rows)) and bool(rows)
        checked = paired and all(o["status"] == "completed" and o["verified"] is True
                                 and len(o["attempts"]) == 1 for o in rows + baseline_rows)
        base_ms = statistics.median(o["response_chain_ms"] for o in baseline_rows)
        candidate_ms = statistics.median(o["response_chain_ms"] for o in rows)
        enough = report["repetitions"] >= 3
        verdict = "needs_quality_review"
        if checked:
            verdict = "insufficient_repetitions" if not enough else (
                "faster_on_these_checks" if candidate_ms < base_ms else "no_measured_gain")
        comparisons.append({"baseline": baseline, "candidate": profile_id,
                            "paired": paired, "all_predicates_passed": checked,
                            "median_latency_ratio": round(base_ms / candidate_ms, 4) if candidate_ms > 0 else None,
                            "verdict": verdict})
    return {"comparisons": comparisons, "automatic_promotion": False,
            "quality_scope": "Task predicates only; not proof of business correctness or decoding equivalence.",
            "measurement_scope": "Sequential non-streaming response latency; includes failed attempts, excludes memory preparation.",
            "speculative_mode_verified": False}


def execute(config, tasks, run_dir, *, profile_ids=None, repetitions=1, external_context=None):
    """Run routed tasks or compare explicitly selected preconfigured endpoints.

    An existing directory is never resumed: an interrupted inference may already
    have run remotely. Only the separate capture operation may be retried.
    """
    validate_config(config)
    validate_tasks(tasks)
    if config["state"] != "ready":
        raise ValueError("Configuration is a draft; fill and validate engine references first")
    if type(repetitions) is not int or not 1 <= repetitions <= 20:
        raise ValueError("Use 1-20 repetitions")
    benchmark = profile_ids is not None
    if benchmark and (not isinstance(profile_ids, list) or not 2 <= len(profile_ids) <= 8
                      or len(set(profile_ids)) != len(profile_ids)):
        raise ValueError("Benchmark requires 2-8 distinct profile ids, baseline first")
    if not benchmark and (len(tasks) != 1 or repetitions != 1):
        raise ValueError("A routed run accepts one task; use benchmark for multiple trials")
    profiles = {p["id"]: p for p in config["profiles"]}
    selected = profile_ids if benchmark else [plan(config, tasks[0]["task"])["profile_id"]]
    if set(selected) - set(profiles):
        raise ValueError("Unknown profile")
    if benchmark and profiles[selected[0]]["mode"] != "direct":
        raise ValueError("The first benchmark profile must be a direct baseline")
    if benchmark and len({profiles[key]["base_url"].rstrip("/") for key in selected}) != len(selected):
        raise ValueError("Benchmark profiles require distinct, independently configured endpoints")
    if len(tasks) * len(selected) * repetitions > 200:
        raise ValueError("At most 200 calls per benchmark")
    possible = set(selected)
    if not benchmark and "fallback_profile" in config:
        possible.add(config["fallback_profile"])
    if config["memory"]["adapter"] != "none" and possible - set(config["memory"]["allowed_profile_ids"]):
        raise ValueError("Memory access is not configured for every selected/fallback profile")
    for key in possible:
        if "api_key_env" in profiles[key]:
            secret(profiles[key]["api_key_env"])
    if config["memory"]["adapter"] == "botte_http":
        secret(config["memory"]["token_env"])

    directory = Path(run_dir)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    run_id = "runtime-" + uuid.uuid4().hex
    start, observed_at = time.monotonic(), time.time()
    state = {"schema": "botte.runtime-state/v1", "run_id": run_id, "status": "started",
             "config_sha256": digest(config), "observed_at": observed_at}
    write_json(directory / "state.json", state)
    contexts, preparations, observations, outputs = {}, {}, [], []
    try:
        for task in tasks:
            before = time.monotonic()
            contexts[task["id"]] = prepare_context(config, task, external_context)
            preparations[task["id"]] = round((time.monotonic() - before) * 1000, 3)
        # Private snapshot is frozen before the first inference. No raw context in report/outbox.
        write_json(directory / "input.private.json", {"tasks": tasks, "contexts": contexts})
        for repeat in range(repetitions):
            # Rotate order to reduce consistent first-profile warm/cold bias; no hidden warmup.
            order = selected[repeat % len(selected):] + selected[:repeat % len(selected)]
            for task in tasks:
                context = contexts[task["id"]]
                messages = messages_for(task, context)
                for profile_id in order:
                    check_context(config, context)
                    before = time.monotonic()
                    attempts, answer, verified, used = [], None, None, profile_id
                    chain = [profile_id]
                    fallback = config.get("fallback_profile")
                    if not benchmark and fallback and fallback != profile_id:
                        chain.append(fallback)
                    for used in chain:
                        check_context(config, context)
                        attempt_start = time.monotonic()
                        try:
                            answer = infer(config, profiles[used], messages)
                            verified = verify(task, answer["text"])
                            error = "predicate_failed" if verified is False else None
                        except RuntimeFailure as failure:
                            answer, verified, error = None, None, str(failure)
                        attempts.append({"profile_id": used, "declared_mode": profiles[used]["mode"],
                                         "capability_status": "declared_unverified", "error": error,
                                         "elapsed_ms": round((time.monotonic() - attempt_start) * 1000, 3)})
                        if error is None:
                            break
                    row = {"task_id": task["id"], "repeat": repeat, "requested_profile": profile_id,
                           "used_profile": used, "messages_sha256": digest(messages),
                           "verification": task["verification"], "verified": verified,
                           "status": "completed" if attempts[-1]["error"] is None else "failed",
                           "attempts": attempts, "response_chain_ms": round((time.monotonic() - before) * 1000, 3),
                           "ttft_ms": None, "prompt_tokens": answer["prompt_tokens"] if answer else None,
                           "completion_tokens": answer["completion_tokens"] if answer else None}
                    observations.append(row)
                    if answer is not None:
                        outputs.append({"task_id": task["id"], "repeat": repeat, "profile_id": profile_id,
                                        "status": row["status"], "text": answer["text"]})
                    # Preserve completed work even if the next request is interrupted.
                    write_json(directory / "observations.json", observations)
                    write_json(directory / "output.private.json", outputs)
        report = {"schema": "botte.runtime-run/v1", "run_id": run_id, "project_id": config["project_id"],
                  "kind": "benchmark" if benchmark else "run", "observed_at": observed_at,
                  "config_sha256": digest(config), "target": config["target"],
                  "profile_order": selected, "repetitions": repetitions,
                  "memory_adapter": config["memory"]["adapter"], "context_preparation_ms": preparations,
                  "context_stats": {key: {"entries": len(value["entries"]), "utf8_bytes": len(encode(value)),
                                           "sha256": digest(value)} for key, value in contexts.items()},
                  "wall_ms": round((time.monotonic() - start) * 1000, 3), "observations": observations,
                  "summary": _summary(observations), "automatic_promotion": False,
                  "remote_hardware_telemetry": "not_collected"}
        if benchmark:
            report["comparison"] = compare(report)
        write_json(directory / "report.json", report)
        if config["memory"]["adapter"] != "none":
            _outbox(config, directory, report)
        state["status"] = "completed" if all(o["status"] == "completed" for o in observations) else "failed"
        write_json(directory / "state.json", state)
        return report
    except Exception:
        state["status"] = "interrupted_or_setup_failed"
        write_json(directory / "state.json", state)
        raise


def _outbox(config, directory, report):
    summary = {"schema": "botte.runtime-observation/v1", "run_id": report["run_id"],
               "config_sha256": report["config_sha256"], "report_sha256": digest(report),
               "summary": report["summary"], "wall_ms": report["wall_ms"],
               "context_preparation_ms": round(sum(report["context_preparation_ms"].values()), 3),
               "context_snapshot_bytes": sum(s["utf8_bytes"] for s in report["context_stats"].values()),
               "context_snapshot_entries": sum(s["entries"] for s in report["context_stats"].values()),
               "speculative_mode_verified": False, "automatic_promotion": False}
    text = encode(summary).decode("utf-8")
    body = {"project_id": config["project_id"], "key": report["run_id"], "request_id": report["run_id"],
            "record": {"text": text, "kind": "observation", "visibility": "private",
                       "source": {"type": "agent", "id": "botte-runtime", "run_id": report["run_id"],
                                  "observed_at": report["observed_at"], "excerpt": text},
                       "subject_ref": "runtime-config:" + report["config_sha256"],
                       "evidence_refs": ["sha256:" + digest(report)], "tags": ["runtime", "unverified-mode"]}}
    validate(SCHEMAS["capture"], body)
    binding = digest({"credential": secret(config["memory"]["token_env"]), "run_id": report["run_id"]}) if config["memory"]["adapter"] == "botte_http" else None
    write_json(directory / "memory-outbox.json", {"schema": "botte.runtime-outbox/v1", "credential_binding": binding,
               "config_sha256": digest(config), "report_sha256": digest(report),
               "body_sha256": digest(body), "body": body})


def capture(config, run_dir):
    """Retry only an identical observation capture; never execute inference here."""
    validate_config(config)
    if config["memory"]["adapter"] != "botte_http":
        raise ValueError("External adapters must ingest the outbox with their existing memory tools")
    directory = Path(run_dir)
    outbox, report = load(directory / "memory-outbox.json"), load(directory / "report.json")
    if (outbox.get("schema") != "botte.runtime-outbox/v1" or outbox.get("config_sha256") != digest(config)
            or outbox.get("report_sha256") != digest(report)
            or outbox.get("body_sha256") != digest(outbox.get("body"))):
        raise ValueError("Outbox/config/report mismatch; do not rewrite or replay another run")
    body = outbox["body"]
    validate(SCHEMAS["capture"], body)
    if body["project_id"] != config["project_id"] or body["request_id"] != report["run_id"]:
        raise ValueError("Outbox scope mismatch")
    if outbox.get("credential_binding") != digest({"credential": secret(config["memory"]["token_env"]),
                                                   "run_id": report["run_id"]}):
        raise ValueError("Memory credential changed; reconcile the existing receipt with the original identity")
    from skills.memory_hub.shared_service import ServiceError
    try:
        receipt = memory_client(config).call("capture", body)
    except ServiceError:
        raise RuntimeFailure("memory_capture_uncertain_retry_same_outbox") from None
    if (not isinstance(receipt, dict) or receipt.get("quarantined") is not True
            or receipt.get("project_id") != config["project_id"] or receipt.get("key") != body["key"]
            or receipt.get("executable_instruction") is not False or receipt.get("version") != 1):
        raise RuntimeFailure("invalid_capture_receipt_retry_same_outbox")
    write_json(directory / "memory-receipt.json", receipt)
    return receipt
