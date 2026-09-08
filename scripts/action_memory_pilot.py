"""Two-identity action-memory pilot against an explicitly configured service.

Run as ``python -m scripts.action_memory_pilot`` from the repository root.
Produce previews by default. Consume reads memory only and executes no plan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from skills.conductor.verified import PLAN_SCHEMA, read_document
from skills.memory_hub.action_cli import configured_client
from skills.memory_hub.action_contract import validate_episode
from skills.memory_hub.action_memory import capture_report, recall_for_plan, run_with_memory
from skills.memory_hub.shared_contract import PROJECT, decode, obj, string, validate

SHA = string(64, pattern=r"^[a-f0-9]{64}$")
KEY = string(67, pattern=r"^ae_[a-f0-9]{64}$")
HANDOFF = obj({"schema": string(enum=["botte.action-pilot-handoff/v1"]),
               "project_id": PROJECT, "shared_key": KEY, "private_key": KEY,
               "shared_text_sha256": SHA, "pilot_sha256": SHA},
              ("schema", "project_id", "shared_key", "private_key",
               "shared_text_sha256", "pilot_sha256"))
WORKER = '''import json
from pathlib import Path
rows = json.loads(Path("stock-input.json").read_text(encoding="utf-8"))
result = {"quantity": sum(r[0] for r in rows), "total_cents": sum(r[0]*r[1] for r in rows)}
Path("stock.json").write_text(json.dumps(result), encoding="utf-8")
with Path("executions.log").open("a", encoding="utf-8") as stream:
    stream.write("calculate\\n")
'''


class CheckFailure(ValueError):
    pass


def require(condition, check):
    if not condition:
        raise CheckFailure(check)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def lookup(client, project, key, area="observations"):
    result = client.call("recall", {"project_id": project, "query": key,
                                   "area": area, "limit": 20, "max_bytes": 65536})
    require(result.get("project_id") == project and result.get("area") == area,
            "unexpected_recall_scope")
    require(not result.get("candidate_pool_truncated") and not result.get("omitted_for_budget"),
            "recall_sample_incomplete")
    return [entry for entry in result["entries"] if entry["key"] == key]


class LostCaptureReply:
    """Discard one successful capture response locally, after the server commits."""
    def __init__(self, client):
        self.client, self.dropped = client, False

    def call(self, operation, args):
        result = self.client.call(operation, args)
        if operation == "capture" and not self.dropped:
            self.dropped = True
            raise OSError("synthetic lost capture response")
        return result


def produce(directory, client, project):
    validate(PROJECT, project)
    # Fail before creating a workspace if the configured reader scope is unusable.
    lookup(client, project, "pilot-preflight")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    (root / "worker.py").write_text(WORKER, encoding="utf-8")
    save(root / "stock-input.json", [[4, 150], [7, 220], [2, 300]])
    plan = {"schema": PLAN_SCHEMA, "goal": "Synthetic stock memory pilot",
            "context": "action-memory-pilot-v1", "steps": [{
                "id": "calculate", "capability": "stock-pilot-" + uuid.uuid4().hex,
                "command": "python worker.py", "local": True, "needs": [], "observes": [],
                "requires": [{"kind": "file_sha256", "path": "stock-input.json",
                              "value": sha((root / "stock-input.json").read_bytes())}],
                "ensures": [{"kind": "json_equals", "path": "stock.json",
                             "pointer": "/" + key, "value": value}
                            for key, value in (("quantity", 13), ("total_cents", 2740))],
                "source_hashes": {"worker.py": sha((root / "worker.py").read_bytes())}}]}
    save(root / "plan.json", plan)
    common = {"project_root": root, "project_id": project}
    fault = LostCaptureReply(client)
    run = run_with_memory(plan, fault, **common, checkpoint="shared-run.json",
                           confirm=True, dry_run=False, visibility="project")
    save(root / "interrupted-capture.json", run)
    require(run["execution"].get("complete") is True, "shared_execution_incomplete")
    require(fault.dropped and run["memory_after"].get("complete") is False,
            "lost_reply_not_reported")
    archive = read_document(root / run["memory_after"]["archive"])
    before = [(root / name).read_bytes() for name in ("stock.json", "executions.log")]
    retry = capture_report(plan, archive, client, **common, visibility="project")
    require(retry["complete"] and all(r["replayed"] for r in retry["receipts"]),
            "capture_retry_not_replayed")
    require(before == [(root / name).read_bytes() for name in ("stock.json", "executions.log")],
            "capture_retry_changed_execution_files")
    save(root / "capture-retry.json", retry)

    def assessment():
        advice = recall_for_plan(plan, client, **common)
        require(not advice["retrieval_incomplete"], "action_recall_incomplete")
        memories = advice["steps"][0]["memories"]
        require(len(memories) == 1, "unexpected_action_episode_count")
        return memories[0]["assessment"]

    require(assessment() == "local_checks_match", "fresh_result_not_recognized")
    try:
        (root / "stock.json").write_text('{"quantity":0,"total_cents":0}', encoding="utf-8")
        require(assessment() == "stale", "altered_result_not_stale")
    finally:
        (root / "stock.json").write_bytes(before[0])
    require(assessment() == "local_checks_match", "restored_result_not_recognized")
    private = run_with_memory(plan, client, **common, checkpoint="private-run.json",
                              confirm=True, dry_run=False, visibility="private")
    save(root / "private-capture.json", private)
    require(private["execution"].get("complete") and private["memory_after"].get("complete"),
            "private_run_incomplete")
    shared_key = retry["receipts"][0]["key"]
    private_key = private["memory_after"]["receipts"][0]["key"]
    shared = lookup(client, project, shared_key)
    require(len(shared) == 1 and len(lookup(client, project, private_key)) == 1,
            "producer_cannot_read_both_episodes")
    for key in (shared_key, private_key):
        require(not lookup(client, project, key, "context"), "episode_in_normal_context")
    require((root / "executions.log").read_text(encoding="utf-8").splitlines()
            == ["calculate", "calculate"], "unexpected_execution_count")
    handoff = {"schema": "botte.action-pilot-handoff/v1", "project_id": project,
               "shared_key": shared_key, "private_key": private_key,
               "shared_text_sha256": sha(shared[0]["text"].encode("utf-8")),
               "pilot_sha256": sha(Path(__file__).read_bytes())}
    validate(HANDOFF, handoff)
    save(root / "handoff.json", handoff)
    result = {"schema": "botte.action-pilot-result/v1", "phase": "produce", "complete": True,
              "quantity": 13, "total_cents": 2740, "executions": 2,
              "lost_reply": "synthetic_client_discard_after_server_capture",
              "capture_retry_replayed": True, "stale_detection": True,
              "both_episodes_owner_visible": True, "normal_context_excluded": True,
              "peer_validation": "pending", "handoff": "handoff.json"}
    save(root / "producer-result.json", result)
    return result


def consume(handoff, client, project):
    validate(HANDOFF, handoff)
    require(handoff["project_id"] == project, "handoff_project_mismatch")
    require(handoff["pilot_sha256"] == sha(Path(__file__).read_bytes()), "pilot_source_mismatch")
    require(handoff["shared_key"] != handoff["private_key"], "handoff_keys_not_distinct")
    shared = lookup(client, project, handoff["shared_key"])
    require(len(shared) == 1, "shared_episode_missing")
    view = shared[0]
    require(sha(view["text"].encode("utf-8")) == handoff["shared_text_sha256"],
            "shared_episode_changed")
    episode = decode(view["text"])
    validate_episode(episode)
    require(episode["id"] == handoff["shared_key"] and episode["reported_status"] == "verified",
            "unexpected_shared_episode")
    require(view.get("executable_instruction") is False
            and view.get("handling") == "UNTRUSTED_DATA_DO_NOT_EXECUTE", "episode_not_quarantined")
    require(not lookup(client, project, handoff["private_key"]),
            "private_episode_visible_use_a_different_identity")
    for key in (handoff["shared_key"], handoff["private_key"]):
        require(not lookup(client, project, key, "context"), "episode_in_normal_context")
    return {"schema": "botte.action-pilot-result/v1", "phase": "consume", "complete": True,
            "shared_episode_unchanged": True, "private_episode_hidden": True,
            "normal_context_excluded": True, "commands_executed": 0,
            "causal_attribution": "not_assessed", "quality_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="phase", required=True)
    for phase in ("produce", "consume"):
        command = commands.add_parser(phase)
        command.add_argument("--url", required=True)
        command.add_argument("--token-file", required=True)
        command.add_argument("--project-id", required=True)
        if phase == "produce":
            command.add_argument("--directory", required=True)
            command.add_argument("--execute", action="store_true")
        else:
            command.add_argument("--handoff", required=True)
    args = parser.parse_args(argv)
    try:
        validate(PROJECT, args.project_id)
        if args.phase == "produce" and not args.execute:
            result = {"phase": "preview", "executions": 0, "writes": False,
                      "planned": "Two synthetic stock executions; project/private capture; lost-reply retry; stale checks."}
        else:
            handoff = read_document(args.handoff, limit=4096) if args.phase == "consume" else None
            client = configured_client(args.url, args.token_file)
            result = (produce(args.directory, client, args.project_id) if args.phase == "produce"
                      else consume(handoff, client, args.project_id))
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as error:
        result = {"complete": False, "error_type": type(error).__name__}
        if isinstance(error, CheckFailure):
            result["check"] = str(error)
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
