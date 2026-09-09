"""Small two-host smoke kit; observations are not hardware attestation.

All host/config/run files stay private. The offline export copies only fixed
labels, bounded numbers and evidence hashes. It never claims GPU execution,
endpoint-to-host binding, native speculation or a speedup from a smoke call.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import platform
import shutil
import sys
import time
import uuid
from pathlib import Path

from skills.llm_backends.runtime import capture, execute
from skills.llm_backends.runtime_contract import (
    DIGEST, digest, inspect_local, load, obj, plan, string, validate, validate_config,
)
from skills.llm_backends.runtime_io import RuntimeFailure, check_context, messages_for, verify
from skills.memory_hub.shared_contract import encode

CHALLENGE = obj({
    "schema": string(enum=["botte.runtime-challenge/v1"]),
    "nonce": string(32, pattern=r"[0-9a-f]{32}"),
    "config_sha256": DIGEST, "source_sha256": DIGEST,
    "created_at": {"type": "number", "minimum": 1, "maximum": 32503680000},
}, ("schema", "nonce", "config_sha256", "source_sha256", "created_at"))
MAX_AGE = 900


def source_digest():
    root = Path(__file__).resolve().parents[1]
    paths = ["llm_backends/acceptance.py", "llm_backends/runtime.py",
             "llm_backends/runtime_io.py", "llm_backends/runtime_contract.py",
             "memory_hub/shared_contract.py", "memory_hub/shared_http.py", "atomic_json.py"]
    # Git checkouts on Windows may use CRLF; Python reads source with universal newlines.
    return digest({path: hashlib.sha256((root / path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                   for path in paths})


def write_new(path, data):
    """Never replace evidence, follow an existing symlink or print private data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(encode(data).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def challenge_at(path):
    challenge = load(path, 16384)
    validate(CHALLENGE, challenge)
    if challenge["source_sha256"] != source_digest():
        raise ValueError("Collector/runtime sources changed; use the original code on both hosts")
    return challenge


def smoke_task(challenge):
    expected = "runtime-" + challenge["nonce"][:12]
    return {"id": "runtime-smoke", "task": "runtime_acceptance",
            "prompt": "Reply with exactly this text, without quotes or explanation: " + expected,
            "verification": "exact", "expected": expected,
            "memory_query": "runtime acceptance " + challenge["nonce"]}


def baseline(config):
    validate_config(config)
    selected = plan(config, "runtime_acceptance")["profile_id"]
    profile = next(p for p in config["profiles"] if p["id"] == selected)
    if config["state"] != "ready" or profile["mode"] != "direct" or len(profile["device_ids"]) != 1:
        raise ValueError("This smoke kit requires a ready direct profile declaring exactly one target GPU")
    if config.get("fallback_profile", selected) != selected:
        raise ValueError("Disable fallback in the acceptance config; a failed endpoint must stay visible")
    if config["budgets"]["max_output_tokens"] > 256 or config["budgets"]["timeout_seconds"] > 120:
        raise ValueError("Use at most 256 output tokens and a 120-second socket timeout for this smoke")
    return profile


def prepare(config, directory):
    baseline(config)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    challenge = {"schema": "botte.runtime-challenge/v1", "nonce": uuid.uuid4().hex,
                 "config_sha256": digest(config), "source_sha256": source_digest(), "created_at": time.time()}
    write_new(directory / "config.private.json", config)
    write_new(directory / "challenge.json", challenge)
    write_new(directory / "task.json", smoke_task(challenge))
    return {"prepared": True, "network_calls": 0, "inference_attempts": 0,
            "files": ["challenge.json", "config.private.json", "task.json"]}


def host_identity(nonce):
    """Salted OS-installation identity, never a hostname or raw machine ID.

    Different OS installations/VMs may share a physical computer; the export
    deliberately does not equate this observation with physical separation.
    """
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                value = winreg.QueryValueEx(key, "MachineGuid")[0]
        elif sys.platform.startswith("linux"):
            with Path("/etc/machine-id").open(encoding="utf-8") as stream:
                value = stream.read(129).strip()
        else:
            return None
        if not isinstance(value, str) or not 16 <= len(value) <= 128:
            return None
        return hashlib.sha256((nonce + ":" + value.lower()).encode("utf-8")).hexdigest()
    except (OSError, ValueError):
        return None


def collect(challenge, role, storage_path):
    validate(CHALLENGE, challenge)
    if challenge["source_sha256"] != source_digest() or role not in {"controller", "engine"}:
        raise ValueError("Invalid collector role or source revision")
    identity = host_identity(challenge["nonce"])
    if identity is None:
        raise ValueError("OS installation identity unavailable; no two-host observation can be inferred")
    inventory = inspect_local()
    return {"schema": "botte.runtime-host-observation/v1", "role": role,
            "challenge_sha256": digest(challenge), "source_sha256": source_digest(),
            "installation_token": identity, "observed_at": time.time(),
            "os": inventory["os"], "gpu_probe": inventory["gpu_probe"], "devices": inventory["devices"],
            "storage_free_bytes": shutil.disk_usage(storage_path).free,
            "root_free_bytes": shutil.disk_usage(Path(storage_path).resolve().anchor).free}


def _number(value, maximum=2**53 - 1):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError("Invalid measurement")
    return value


def pair(challenge, controller, engine, profile, at):
    for record, role in ((controller, "controller"), (engine, "engine")):
        if (not isinstance(record, dict) or record.get("schema") != "botte.runtime-host-observation/v1"
                or record.get("role") != role or record.get("challenge_sha256") != digest(challenge)
                or record.get("source_sha256") != challenge["source_sha256"]):
            raise ValueError("Host observation is not bound to this challenge, role and source")
        validate(DIGEST, record.get("installation_token"))
        observed = _number(record.get("observed_at"))
        if not -60 <= at - observed <= MAX_AGE:
            raise ValueError("Host observation is stale or in the future; collect a fresh observation")
        _number(record.get("root_free_bytes")); _number(record.get("storage_free_bytes"))
    if controller["installation_token"] == engine["installation_token"]:
        raise ValueError("The two observations came from the same OS installation")
    devices = engine.get("devices")
    if engine.get("gpu_probe") != "observed" or not isinstance(devices, list) or not 1 <= len(devices) <= 16:
        raise ValueError("Engine GPU inventory was not observed")
    selected = [d for d in devices if isinstance(d, dict) and d.get("id") == profile["device_ids"][0]]
    if len(selected) != 1 or _number(selected[0].get("vram_mib"), 2**30) < 1:
        raise ValueError("The declared target GPU is missing from the engine observation")
    return selected[0]


def run(directory, engine_probe, external_context=None, record_memory=False):
    directory = Path(directory)
    challenge = challenge_at(directory / "challenge.json")
    config = load(directory / "config.private.json")
    profile = baseline(config)
    if digest(config) != challenge["config_sha256"]:
        raise ValueError("Acceptance configuration changed; prepare a new package")
    if record_memory and config["memory"]["adapter"] != "botte_http":
        raise ValueError("Recording requires the existing botte_http memory adapter")
    if (directory / "run").exists() or (directory / "attempt.private.json").exists():
        raise ValueError("Acceptance already attempted; inspect it or retry capture only")
    engine = load(engine_probe)
    controller = collect(challenge, "controller", directory)
    pair(challenge, controller, engine, profile, time.time())
    task = smoke_task(challenge)
    if load(directory / "task.json") != task:
        raise ValueError("Synthetic smoke task changed; use the existing runtime for other tasks")
    # The exclusive marker also arbitrates simultaneous attempts before any network call.
    write_new(directory / "attempt.private.json", {"started_at": time.time()})
    write_new(directory / "controller.private.json", controller)
    write_new(directory / "engine.private.json", engine)
    report = execute(config, [task], directory / "run", external_context=external_context)
    if record_memory:
        capture(config, directory / "run")
    return {"smoke_completed": report["observations"][0]["status"] == "completed",
            "inference_attempts": 1, "gpu_execution_verified": False, "speedup_measured": False,
            "next": "export the bounded observation summary; review native engine evidence separately"}


def export(directory):
    """Offline review of known artifacts, without forwarding arbitrary report fields."""
    directory = Path(directory)
    challenge = challenge_at(directory / "challenge.json")
    config = load(directory / "config.private.json")
    profile = baseline(config)
    report = load(directory / "run/report.json")
    controller, engine = (load(directory / name) for name in ("controller.private.json", "engine.private.json"))
    if (digest(config) != challenge["config_sha256"] or report.get("config_sha256") != digest(config)
            or report.get("schema") != "botte.runtime-run/v1" or report.get("kind") != "run"):
        raise ValueError("Run/config/challenge mismatch")
    selected = pair(challenge, controller, engine, profile, _number(report.get("observed_at")))
    task = smoke_task(challenge)
    inputs, outputs = load(directory / "run/input.private.json"), load(directory / "run/output.private.json")
    rows = report.get("observations")
    if inputs.get("tasks") != [task] or not isinstance(rows, list) or len(rows) != 1 or len(outputs) != 1:
        raise ValueError("Expected one unchanged synthetic task and one observation/output")
    row, output = rows[0], outputs[0]
    context = inputs["contexts"][task["id"]]
    check_context(config, context, now=report["observed_at"])
    attempts = row.get("attempts")
    if (row.get("task_id") != task["id"] or row.get("used_profile") != profile["id"]
            or row.get("requested_profile") != profile["id"] or row.get("status") != "completed"
            or row.get("verified") is not True or row.get("verification") != "exact"
            or row.get("messages_sha256") != digest(messages_for(task, context))
            or not isinstance(attempts, list) or len(attempts) != 1
            or attempts[0].get("profile_id") != profile["id"] or attempts[0].get("error") is not None
            or output.get("task_id") != task["id"] or output.get("profile_id") != profile["id"]
            or output.get("status") != "completed" or not isinstance(output.get("text"), str)
            or verify(task, output["text"]) is not True):
        raise ValueError("The recorded response did not pass the one-call smoke predicate")
    memory_receipt = False
    receipt_path = directory / "run/memory-receipt.json"
    if receipt_path.exists():
        receipt = load(receipt_path)
        if (config["memory"]["adapter"] != "botte_http" or receipt.get("project_id") != config["project_id"]
                or receipt.get("key") != report.get("run_id") or receipt.get("quarantined") is not True
                or receipt.get("executable_instruction") is not False or receipt.get("version") != 1):
            raise ValueError("Memory receipt does not match the run")
        memory_receipt = True
    token_count = row.get("completion_tokens")
    if token_count is not None:
        if type(token_count) is not int:
            raise ValueError("Invalid token count")
        _number(token_count, 2**31)
    os_label = lambda value: value if value in {"Linux", "Windows", "Darwin"} else "other"
    return {"schema": "botte.runtime-acceptance-public/v1", "status": "smoke_observations_recorded",
            "source_sha256": challenge["source_sha256"],
            "evidence_sha256": digest({"challenge": challenge, "report": report, "controller": controller, "engine": engine}),
            "observations": {"controller_os": os_label(controller.get("os")), "engine_os": os_label(engine.get("os")),
                             "engine_gpu_count": len(engine["devices"]), "selected_vram_mib": selected["vram_mib"],
                             "engine_root_free_mib": int(engine["root_free_bytes"] // 1048576),
                             "engine_storage_free_mib": int(engine["storage_free_bytes"] // 1048576),
                             "response_ms": _number(row.get("response_chain_ms"), 10**9),
                             "completion_tokens": token_count, "context_entries": len(context["entries"]),
                             "memory_adapter": config["memory"]["adapter"], "memory_receipt_recorded": memory_receipt},
            "claims": {"distinct_os_installations_recorded": True, "response_predicate_checked": True,
                       "selected_gpu_listed": True, "endpoint_host_binding_verified": False,
                       "gpu_execution_verified": False, "speculative_mode_verified": False,
                       "speedup_measured": False, "production_ready": False},
            "limits": ["Collector files are operator evidence, not independent hardware attestation.",
                       "Bind the request to the actual engine process and GPU using native logs/telemetry.",
                       "A smoke response does not establish task quality, remote draft execution or a speedup."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("prepare", help="Prepare a private one-call smoke package; no network")
    init.add_argument("config"); init.add_argument("--directory", required=True)
    probe = commands.add_parser("collect", help="Collect local host observations; no network")
    probe.add_argument("challenge"); probe.add_argument("--role", choices=["controller", "engine"], required=True)
    probe.add_argument("--storage-path", default="."); probe.add_argument("--output", required=True)
    attempt = commands.add_parser("run", help="One direct call on the controller; no remote installation")
    attempt.add_argument("directory"); attempt.add_argument("--engine-probe", required=True)
    attempt.add_argument("--context"); attempt.add_argument("--record-memory", action="store_true")
    public = commands.add_parser("export", help="Offline, allowlisted summary only")
    public.add_argument("directory"); public.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(load(args.config), args.directory)
        elif args.command == "collect":
            write_new(args.output, collect(challenge_at(args.challenge), args.role, args.storage_path))
            result = {"collected": True, "role": args.role, "network_calls": 0}
        elif args.command == "run":
            result = run(args.directory, args.engine_probe, load(args.context) if args.context else None, args.record_memory)
        else:
            result = export(args.directory)
            write_new(args.output, result)
        print(encode(result).decode("utf-8"))
        return 1 if args.command == "run" and not result["smoke_completed"] else 0
    except (ValueError, RuntimeFailure, OSError, KeyError, TypeError, AttributeError, RecursionError) as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeFailure)) else "invalid_or_unavailable_local_evidence"
        print(encode({"error": message}).decode("utf-8"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
