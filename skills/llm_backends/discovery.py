"""LLM Backend Discovery — find local model servers on this machine and the network.

Pure stdlib (urllib + socket + concurrent.futures). No external deps, works on
Windows / macOS / Linux. Probes well-known local-inference servers and, for the
OpenAI-compatible ones, enumerates the models they expose.

Supported backends (default ports):
    LM Studio        1234   /v1/models           (OpenAI-compatible)
    Ollama           11434  /api/tags  + /v1      (native + OpenAI-compatible)
    LocalAI          8080   /v1/models
    vLLM             8000   /v1/models
    llama.cpp server 8080   /v1/models
    Jan              1337   /v1/models
    KoboldCpp        5001   /v1/models
    text-gen-webui   5000   /v1/models
    Open WebUI       3000   /api/models
    ComfyUI          8188   /system_stats         (image generation)
    Qdrant           6333   /collections          (vector search)

Token impact: every task served locally is a task NOT sent to the cloud.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Backend probe definitions ───────────────────────────────────────────────

@dataclass(frozen=True)
class Probe:
    """How to detect one kind of backend on a host:port."""
    kind: str               # backend identifier, e.g. "lmstudio"
    label: str              # human label
    port: int               # default port
    path: str               # HTTP path to probe
    api: str                # "openai" | "ollama" | "comfyui" | "qdrant"
    chat: bool              # exposes an OpenAI-compatible chat endpoint?


# Order matters only for display. Ports can be overridden per-host at scan time.
PROBES: tuple[Probe, ...] = (
    Probe("lmstudio",   "LM Studio",        1234,  "/v1/models",     "openai",  True),
    Probe("ollama",     "Ollama",           11434, "/api/tags",      "ollama",  True),
    Probe("localai",    "LocalAI",          8080,  "/v1/models",     "openai",  True),
    Probe("vllm",       "vLLM",             8000,  "/v1/models",     "openai",  True),
    Probe("jan",        "Jan",              1337,  "/v1/models",     "openai",  True),
    Probe("koboldcpp",  "KoboldCpp",        5001,  "/v1/models",     "openai",  True),
    Probe("textgenui",  "text-gen-webui",   5000,  "/v1/models",     "openai",  True),
    Probe("openwebui",  "Open WebUI",       3000,  "/api/models",    "openai",  False),
    Probe("comfyui",    "ComfyUI",          8188,  "/system_stats",  "comfyui", False),
    Probe("qdrant",     "Qdrant",           6333,  "/collections",   "qdrant",  False),
)


# ── Discovered backend record ────────────────────────────────────────────────

@dataclass
class Backend:
    """A live backend found during discovery."""
    kind: str
    label: str
    host: str
    port: int
    api: str
    chat: bool
    models: list[str] = field(default_factory=list)
    latency_ms: int = 0
    base_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Low-level HTTP (stdlib only) ─────────────────────────────────────────────

def _http_get(url: str, timeout: float) -> Optional[dict]:
    """GET a JSON endpoint. Returns parsed JSON or None on any failure."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _port_open(host: str, port: int, timeout: float) -> bool:
    """Fast TCP check before doing the (slower) HTTP probe."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _extract_models(api: str, payload: dict) -> list[str]:
    """Pull model ids out of a probe response, per API shape."""
    if payload is None:
        return []
    if api == "openai":
        data = payload.get("data", payload.get("models", []))
        out = []
        for m in data if isinstance(data, list) else []:
            if isinstance(m, dict):
                out.append(m.get("id") or m.get("name") or "")
            elif isinstance(m, str):
                out.append(m)
        return [m for m in out if m]
    if api == "ollama":
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
    return []


# ── Single-host probing ──────────────────────────────────────────────────────

def probe_host(host: str, probe: Probe, port: Optional[int] = None,
               timeout: float = 1.5) -> Optional[Backend]:
    """Probe one host for one backend kind. Returns a Backend or None."""
    port = port or probe.port
    if not _port_open(host, port, timeout):
        return None

    base = f"http://{host}:{port}"
    t0 = time.perf_counter()
    payload = _http_get(base + probe.path, timeout)
    latency = int((time.perf_counter() - t0) * 1000)
    if payload is None:
        return None

    models = _extract_models(probe.api, payload)
    return Backend(
        kind=probe.kind, label=probe.label, host=host, port=port,
        api=probe.api, chat=probe.chat, models=models,
        latency_ms=latency, base_url=base,
    )


def scan_host(host: str, timeout: float = 1.5,
              probes: tuple[Probe, ...] = PROBES) -> list[Backend]:
    """Probe a single host for every known backend, in parallel."""
    found: list[Backend] = []
    with ThreadPoolExecutor(max_workers=len(probes)) as pool:
        futures = {pool.submit(probe_host, host, p, None, timeout): p for p in probes}
        for fut in as_completed(futures):
            backend = fut.result()
            if backend:
                found.append(backend)
    return sorted(found, key=lambda b: (b.host, b.port))


# ── Network helpers ──────────────────────────────────────────────────────────

def local_ipv4() -> Optional[str]:
    """Best-effort local IPv4 of this machine (no traffic actually sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def subnet_hosts(cidr_base: Optional[str] = None) -> list[str]:
    """Return the 254 usable hosts of the local /24 (or a given x.y.z base)."""
    if cidr_base is None:
        ip = local_ipv4()
        if not ip:
            return []
        cidr_base = ".".join(ip.split(".")[:3])
    return [f"{cidr_base}.{i}" for i in range(1, 255)]


# ── Top-level discovery ──────────────────────────────────────────────────────

def discover(hosts: Optional[list[str]] = None,
             scan_subnet: bool = False,
             timeout: float = 1.0,
             max_workers: int = 64) -> list[Backend]:
    """Discover backends across hosts.

    Args:
        hosts: explicit hosts to probe (default: ["127.0.0.1"]).
        scan_subnet: also sweep the local /24 (slower, parallelised).
        timeout: per-probe socket/HTTP timeout in seconds.
        max_workers: parallelism for the subnet sweep.
    """
    targets: list[str] = list(hosts) if hosts else ["127.0.0.1"]
    if scan_subnet:
        for h in subnet_hosts():
            if h not in targets:
                targets.append(h)

    results: list[Backend] = []
    # Flatten (host, probe) pairs and run them all in one pool for speed.
    pairs = [(h, p) for h in targets for p in PROBES]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(probe_host, h, p, None, timeout): (h, p)
            for (h, p) in pairs
        }
        for fut in as_completed(futures):
            backend = fut.result()
            if backend:
                results.append(backend)

    return sorted(results, key=lambda b: (b.host, b.port))


if __name__ == "__main__":
    import sys
    scan = "--subnet" in sys.argv
    extra = [a for a in sys.argv[1:] if not a.startswith("--")]
    hosts = extra or None
    print(f"🔍 Discovering LLM backends (subnet={scan})...")
    found = discover(hosts=hosts, scan_subnet=scan)
    if not found:
        print("  (none found — is LM Studio / Ollama running?)")
    for b in found:
        models = ", ".join(b.models[:3]) + (" …" if len(b.models) > 3 else "")
        print(f"  ✅ {b.label:16s} {b.host}:{b.port}  {b.latency_ms}ms  [{models}]")
