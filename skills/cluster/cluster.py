"""Cluster — treat the homelab as one schedulable resource.

Idle local capacity is recovered cost: instead of always hitting the same
backend (or the cloud), spread cheap work across every reachable machine and
prefer the least-recently-used one, so idle boxes get the next task.

  machines()   group discovered backends by host (the cluster view)
  pick()       choose a chat backend across machines — 'lru' spreads work to
               idle machines, 'latency' picks the most responsive
  status()     overview + recommended target
  delegate()   hand a task to a machine's agent endpoint (Hermes plugs in here)

The delegation is a *hand-off only* — it never runs privileged maintenance
itself. Wire a trusted agent (e.g. Hermes) on each machine to receive tasks.
Pure stdlib.
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from skills.llm_backends import registry
from skills.llm_backends.discovery import Backend

_STATE = Path.home() / ".botte-cluster.json"


@dataclass
class Machine:
    host: str
    backends: list           # list[dict]
    chat_models: list = field(default_factory=list)
    min_latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def machines(scan_subnet: bool = False, fresh: bool = False) -> list[Machine]:
    backends = (registry.refresh(scan_subnet=scan_subnet) if fresh
                else (registry.load() or registry.refresh(scan_subnet=scan_subnet)))
    by_host: dict[str, list[Backend]] = {}
    for b in backends:
        by_host.setdefault(b.host, []).append(b)
    out = []
    for host, bs in by_host.items():
        chat_models = sorted({m for b in bs if b.chat for m in b.models})
        out.append(Machine(host=host, backends=[b.to_dict() for b in bs],
                           chat_models=chat_models,
                           min_latency_ms=min((b.latency_ms for b in bs), default=0)))
    return sorted(out, key=lambda m: m.min_latency_ms)


# ── state for LRU spreading ──────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _chat_backends() -> list[Backend]:
    return [b for b in registry.chat_backends() if b.models]


def pick(strategy: str = "lru") -> Optional[dict]:
    """Pick a chat backend across the cluster.

    - 'lru'     : least-recently-used capable backend → spreads work to idle boxes.
    - 'latency' : lowest-latency (most responsive) backend.
    Records the choice so the next 'lru' call avoids it.
    """
    cands = _chat_backends()
    if not cands:
        return None
    if strategy == "latency":
        chosen = min(cands, key=lambda b: b.latency_ms)
    else:
        state = _load_state()
        last = state.get("last_used", {})
        # smallest last-used timestamp wins (never-used = 0)
        chosen = min(cands, key=lambda b: last.get(f"{b.host}:{b.port}", 0))
        last[f"{chosen.host}:{chosen.port}"] = time.time()
        state["last_used"] = last
        _save_state(state)
    return {"host": chosen.host, "port": chosen.port, "label": chosen.label,
            "base_url": chosen.base_url, "model": registry.preferred_model(chosen),
            "latency_ms": chosen.latency_ms, "strategy": strategy}


def status(scan_subnet: bool = False) -> dict:
    ms = machines(scan_subnet=scan_subnet, fresh=scan_subnet)
    chat = _chat_backends()
    return {
        "machines": [m.to_dict() for m in ms],
        "machine_count": len(ms),
        "chat_capable": [f"{b.host}:{b.port}" for b in chat],
        "recommended_lru": pick("lru") if chat else None,
        "recommended_fastest": pick("latency") if chat else None,
    }


# ── delegation hand-off (Hermes plugs in) ────────────────────────────────────

def _env_suffix(host: str) -> str:
    return host.replace(".", "_").replace(":", "_").replace("-", "_")


def _is_loopback(host: str) -> bool:
    normalized = host.strip("[]").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _resolve_agent_url(host: str, provided: Optional[str]) -> tuple[str, str]:
    """Resolve and validate the endpoint before it reaches the network sink."""
    key = "BOTTE_AGENT_" + _env_suffix(host)
    raw = provided or os.environ.get(key, "")
    if not raw:
        return "", f"no agent endpoint for {host} (set {key} or pass agent_url)"
    try:
        parsed = urllib.parse.urlsplit(raw)
        endpoint_port = parsed.port
    except ValueError as exc:
        return "", f"invalid agent endpoint: {exc}"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "", "agent endpoint must use http or https and include a host"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "", "agent endpoint must not contain credentials, query, or fragment"
    expected = host.strip("[]").casefold()
    if parsed.hostname.casefold() != expected:
        return "", "agent endpoint host must match the delegated machine"
    if parsed.path not in {"", "/task"}:
        return "", "agent endpoint path must be /task"
    if not _is_loopback(expected) and parsed.scheme != "https":
        return "", "non-loopback agent endpoints require https"
    netloc = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    if endpoint_port is not None:
        netloc += f":{endpoint_port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, "/task", "", "")), ""


def _resolve_agent_token(host: str, provided: Optional[str]) -> str:
    suffix = _env_suffix(host)
    return (provided or os.environ.get(f"BOTTE_AGENT_TOKEN_{suffix}")
            or os.environ.get("BOTTE_AGENT_TOKEN", ""))


def delegate(host: str, task: str, *, agent_url: Optional[str] = None,
             token: Optional[str] = None, timeout: float = 30.0) -> dict:
    """Hand a task to a trusted agent on `host` (does NOT run maintenance itself).

    Posts {"task": ...} to the machine's agent endpoint. The endpoint is provided
    explicitly or via env BOTTE_AGENT_<host-with-underscores>. If none is
    configured, returns a no-op result describing how to wire one.
    """
    agent_url, error = _resolve_agent_url(host, agent_url)
    if error:
        return {"delegated": False, "host": host,
                "reason": error}
    token = _resolve_agent_token(host, token)
    if not _is_loopback(host) and not token:
        return {"delegated": False, "host": host,
                "reason": "non-loopback agent endpoints require a token"}
    body = json.dumps({"task": task, "from": "botte-cluster",
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Botte-Token"] = token
    req = urllib.request.Request(agent_url, data=body, method="POST",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"delegated": True, "host": host, "agent_url": agent_url,
                    "response": r.read().decode("utf-8", "replace")[:1000]}
    except (urllib.error.URLError, OSError) as e:
        return {"delegated": False, "host": host, "agent_url": agent_url, "error": str(e)}
