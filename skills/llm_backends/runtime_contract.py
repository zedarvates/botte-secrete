"""Portable, offline contract for task-specific local inference profiles.

Profiles describe already configured engines. A declaration is not a probe,
proof of speculative decoding, a model installer, or a hardware reservation.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import os
import platform
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from skills.memory_hub.shared_contract import (
    IDENTIFIER, PROJECT, decode, encode, obj, string, validate,
)

VERSION = "botte.runtime/v1"
DIGEST = string(64, pattern=r"[0-9a-f]{64}")
ENV = string(128, pattern=r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def array(items, maximum=32, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


DRAFT = obj({
    "host_id": IDENTIFIER, "device_ids": array(IDENTIFIER, 16),
    "model": string(), "revision": string(), "compatibility_ref": string(),
}, ("host_id", "device_ids", "model", "revision", "compatibility_ref"))
PROFILE = obj({
    "id": IDENTIFIER, "host_id": IDENTIFIER, "device_ids": array(IDENTIFIER, 16),
    "mode": string(enum=["direct", "speculative_local", "speculative_remote"]),
    "base_url": string(2048), "api_key_env": ENV,
    "engine_revision": string(), "engine_config_sha256": DIGEST,
    "drafts": array(DRAFT, 8),
}, ("id", "host_id", "device_ids", "mode", "base_url", "engine_revision",
    "engine_config_sha256", "drafts"))
SCHEMA = obj({
    "schema": string(enum=[VERSION]), "state": string(enum=["draft", "ready"]),
    "project_id": PROJECT,
    "hosts": array(obj({
        "id": IDENTIFIER,
        "devices": array(obj({"id": IDENTIFIER, "vram_mib": integer(1, 2**30)},
                             ("id", "vram_mib")), 16),
    }, ("id", "devices")), 32, 1),
    "target": obj({"model": string(), "revision": string(), "quantization": string()},
                  ("model", "revision", "quantization")),
    "profiles": array(PROFILE, 32, 1), "default_profile": IDENTIFIER,
    "task_routes": array(obj({"task": IDENTIFIER, "profile_id": IDENTIFIER},
                             ("task", "profile_id"))),
    "fallback_profile": IDENTIFIER,
    "memory": obj({
        "adapter": string(enum=["none", "botte_http", "external"]),
        "url": string(2048), "token_env": ENV,
        "allowed_profile_ids": array(IDENTIFIER),
    }, ("adapter", "allowed_profile_ids")),
    "budgets": obj({
        "max_context_bytes": integer(1024, 65536),
        "max_output_tokens": integer(1, 8192),
        "timeout_seconds": integer(1, 600),
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
    }, ("max_context_bytes", "max_output_tokens", "timeout_seconds", "temperature")),
}, ("schema", "state", "project_id", "hosts", "target", "profiles",
    "default_profile", "task_routes", "memory", "budgets"))

TASK = obj({
    "id": IDENTIFIER, "task": IDENTIFIER, "prompt": string(64000),
    "system": string(4000), "memory_query": string(2000),
    "verification": string(enum=["none", "exact", "json", "python_syntax"]),
    "expected": string(64000),
}, ("id", "task", "prompt", "verification"))
TASKS = array(TASK, 100, 1)
CONTEXT = obj({
    "schema": string(enum=["botte.runtime-context/v1"]), "project_id": PROJECT,
    "entries": array(obj({
        "key": string(), "version": string(), "text": string(16000),
        "source_ref": string(), "expires_at": {"type": "number", "minimum": 1},
    }, ("key", "version", "text", "source_ref", "expires_at")), 20),
}, ("schema", "project_id", "entries"))


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def load(path, limit=1_048_576):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("JSON file exceeds size limit")
    return decode(data)


def endpoint(url, *, memory=False):
    """No credentials, redirects/proxies, or plaintext non-loopback traffic."""
    parsed = urllib.parse.urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or any(c.isspace() for c in url)):
        raise ValueError("Endpoint must have a host and no credentials, query or fragment")
    local = parsed.hostname == "localhost"
    try:
        local = local or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise ValueError("Use HTTPS remotely, or an HTTP loopback SSH tunnel")
    if memory and parsed.path not in {"", "/"}:
        raise ValueError("Memory endpoint must be a bare origin")
    if not memory and parsed.path.rstrip("/") != "/v1":
        raise ValueError("Inference base_url must end in /v1")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid endpoint port")
    return local


def _unique(items, key, label):
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate {label}")
    return result


def validate_config(config):
    validate(SCHEMA, config, "config")
    hosts = _unique(config["hosts"], "id", "host")
    devices = {key: _unique(host["devices"], "id", "device") for key, host in hosts.items()}
    profiles = _unique(config["profiles"], "id", "profile")

    def placement(item):
        host, ids = item["host_id"], item["device_ids"]
        if host not in hosts or len(set(ids)) != len(ids) or set(ids) - set(devices[host]):
            raise ValueError("Unknown or duplicate host/device placement")

    for profile in profiles.values():
        placement(profile)
        local = endpoint(profile["base_url"])
        if not local and "api_key_env" not in profile:
            raise ValueError("Remote inference requires an api_key_env reference")
        drafts, mode = profile["drafts"], profile["mode"]
        if (mode == "direct") != (len(drafts) == 0):
            raise ValueError("Only speculative profiles declare drafts")
        for draft in drafts:
            placement(draft)
        remote = any(d["host_id"] != profile["host_id"] for d in drafts)
        if mode == "speculative_local" and remote or mode == "speculative_remote" and not remote:
            raise ValueError("Draft placement does not match the declared mode")
        if config["state"] == "ready" and (
                profile["engine_config_sha256"] == "0" * 64
                or profile["engine_revision"] in {"replace-me", "unknown", "latest"}
                or any(d[field] in {"replace-me", "unknown", "latest"}
                       for d in drafts for field in ("model", "revision", "compatibility_ref"))):
            raise ValueError("Ready profiles require pinned engine/config/draft references")
    routes = _unique(config["task_routes"], "task", "task route")
    refs = [config["default_profile"], *(r["profile_id"] for r in routes.values())]
    if "fallback_profile" in config:
        refs.append(config["fallback_profile"])
    refs.extend(config["memory"]["allowed_profile_ids"])
    if set(refs) - set(profiles):
        raise ValueError("Unknown profile reference")
    if "fallback_profile" in config and profiles[config["fallback_profile"]]["mode"] != "direct":
        raise ValueError("Fallback must be a direct profile for the same target")
    memory = config["memory"]
    if memory["adapter"] == "botte_http":
        if not {"url", "token_env"} <= set(memory):
            raise ValueError("Botte memory requires url and token_env")
        endpoint(memory["url"], memory=True)
    elif set(memory) != {"adapter", "allowed_profile_ids"}:
        raise ValueError("Only botte_http accepts memory credentials and an endpoint")
    if config["state"] == "ready" and any(
            v in {"replace-me", "unknown", "latest"} for v in config["target"].values()):
        raise ValueError("Pin the target model, revision and quantization before execution")
    return config


def validate_tasks(tasks):
    validate(TASKS, tasks, "tasks")
    _unique(tasks, "id", "task id")
    for task in tasks:
        if (task["verification"] == "exact") != ("expected" in task):
            raise ValueError("Only exact verification requires expected text")
    return tasks


def plan(config, task="chat", profile_id=None):
    validate_config(config)
    selected = profile_id or next((r["profile_id"] for r in config["task_routes"]
                                   if r["task"] == task), config["default_profile"])
    profiles = {p["id"]: p for p in config["profiles"]}
    if selected not in profiles:
        raise ValueError("Unknown profile")
    profile = profiles[selected]
    return {"schema": VERSION, "project_id": config["project_id"], "task": task,
            "profile_id": selected, "declared_mode": profile["mode"],
            "capability_status": "declared_unverified", "ready": config["state"] == "ready",
            "config_sha256": digest(config), "target": config["target"],
            "target_host": profile["host_id"], "target_devices": profile["device_ids"],
            "draft_hosts": [d["host_id"] for d in profile["drafts"]],
            "memory_adapter": config["memory"]["adapter"],
            "fallback_profile": config.get("fallback_profile"),
            "network_calls": 0, "hardware_reserved": False, "automatic_promotion": False}


def template(topology="single", memory="none"):
    if topology not in {"single", "local-draft", "remote-draft"} or memory not in {"none", "botte_http", "external"}:
        raise ValueError("Unsupported template")
    baseline = {"id": "baseline", "host_id": "worker-a", "device_ids": [],
                "mode": "direct", "base_url": "http://127.0.0.1:8080/v1",
                "engine_revision": "replace-me", "engine_config_sha256": "0" * 64, "drafts": []}
    config = {"schema": VERSION, "state": "draft", "project_id": "my-project",
              "hosts": [{"id": "worker-a", "devices": []}],
              "target": {"model": "replace-me", "revision": "replace-me", "quantization": "replace-me"},
              "profiles": [baseline], "default_profile": "baseline", "task_routes": [],
              "memory": {"adapter": memory, "allowed_profile_ids": ["baseline"]},
              "budgets": {"max_context_bytes": 8192, "max_output_tokens": 512,
                          "timeout_seconds": 60, "temperature": 0}}
    if topology != "single":
        candidate = copy.deepcopy(baseline)
        candidate.update(id="candidate", base_url="http://127.0.0.1:8081/v1",
                         mode="speculative_local" if topology == "local-draft" else "speculative_remote")
        host_id = "worker-a" if topology == "local-draft" else "worker-b"
        if topology == "remote-draft":
            config["hosts"].append({"id": host_id, "devices": []})
        candidate["drafts"] = [{"host_id": host_id, "device_ids": [], "model": "replace-me",
                                "revision": "replace-me", "compatibility_ref": "replace-me"}]
        config["profiles"].append(candidate)
        config["memory"]["allowed_profile_ids"].append("candidate")
        config["fallback_profile"] = "baseline"
    if memory == "botte_http":
        config["memory"].update(url="http://127.0.0.1:8765", token_env="BOTTE_MEMORY_TOKEN")
    return validate_config(config)


def inspect_local():
    """Read this host only; inventory does not assume aggregate VRAM is usable."""
    from skills.llm_backends.audit import _total_ram_gb
    result = {"schema": "botte.runtime-inventory/v1", "os": platform.system(),
              "architecture": platform.machine(), "logical_cpus": os.cpu_count(),
              "ram_gib": _total_ram_gb(), "devices": [], "gpu_probe": "unavailable",
              "network_calls": 0, "scope": "current_host_only"}
    if shutil.which("nvidia-smi"):
        try:
            probe = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free",
                                    "--format=csv,noheader,nounits"], capture_output=True,
                                   text=True, encoding="utf-8", timeout=5, check=True)
            for row in probe.stdout.splitlines():
                index, name, total, free = [p.strip() for p in row.split(",")]
                result["devices"].append({"id": "gpu-" + index, "name": name,
                                          "vram_mib": int(total), "free_vram_mib": int(free)})
            result["gpu_probe"] = "observed"
        except (OSError, ValueError, subprocess.SubprocessError):
            result["devices"] = []
            result["gpu_probe"] = "failed"
    return result
