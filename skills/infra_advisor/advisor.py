"""Infra advisor — hardware / software / MCP tips to cut token cost on a cluster.

Audits don't just look at code. This looks at the *machine and the local cluster*
and recommends concrete changes that move work off paid cloud models:

  - add/upgrade a GPU so a 7-14B coder runs locally
  - add a Hailo-8/8L/10 NPU for ~0-token vision (detection / OCR)
  - move the always-on inference node to Linux server (no forced Windows
    reboots/updates killing the endpoint; less RAM overhead)
  - run Qdrant locally to unlock the semantic response cache (-60% repeats)
  - dedicate the strongest host as a shared inference node for many projects
  - wire the MCP server into the project so the agent actually uses local tools

Renders an ASCII cluster diagram by default. Pure stdlib.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from skills.llm_backends.audit import profile_hardware, Hardware
from skills.llm_backends import registry
from skills.llm_backends.discovery import Backend


@dataclass
class Tip:
    priority: str       # P0 (do first) .. P3 (nice to have)
    category: str       # hardware | software | infra | mcp
    title: str
    why: str
    impact: str         # expected token/cost effect

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Snapshot:
    hardware: dict
    backends: list           # list[dict]
    cloud_keys: list
    network_hosts: list      # distinct hosts seen in registry
    mcp_wired: bool


# ── gather facts ──────────────────────────────────────────────────────────────

def _cloud_keys() -> list:
    env = ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
           "ZHIPUAI_API_KEY", "NVIDIA_API_KEY")
    return [k for k in env if os.environ.get(k)]


def _mcp_wired(project: Path) -> bool:
    p = project / ".mcp.json"
    if not p.exists():
        return False
    try:
        return "botte-llm" in json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return False


def gather(project: Optional[Path] = None, scan_subnet: bool = False,
           fresh: bool = False) -> Snapshot:
    backends = registry.refresh(scan_subnet=scan_subnet) if fresh else (
        registry.load() or registry.refresh(scan_subnet=scan_subnet))
    hw = profile_hardware()
    hosts = sorted({b.host for b in backends})
    return Snapshot(
        hardware=hw.to_dict(), backends=[b.to_dict() for b in backends],
        cloud_keys=_cloud_keys(), network_hosts=hosts,
        mcp_wired=_mcp_wired(project or Path.cwd()),
    )


# ── recommendation rules ──────────────────────────────────────────────────────

def _has_kind(backends: list, kind: str) -> bool:
    return any(b.get("kind") == kind for b in backends)


def _has_chat(backends: list) -> bool:
    return any(b.get("chat") and b.get("models") for b in backends)


def recommend(snap: Snapshot) -> list[Tip]:
    tips: list[Tip] = []
    hw = snap.hardware
    vram = float(hw.get("vram_gb", 0) or 0)
    ram = float(hw.get("ram_gb", 0) or 0)
    os_name = str(hw.get("os", ""))
    backends = snap.backends

    # --- the foundation ---
    if not _has_chat(backends):
        tips.append(Tip("P0", "software", "Install a local LLM server (LM Studio or Ollama)",
                        "No local chat endpoint was found — every other saving below depends on one.",
                        "Unlocks 0-token local routing for cheap tasks."))

    # --- GPU / VRAM ---
    if vram == 0:
        tips.append(Tip("P1", "hardware", "Add a GPU with ≥12 GB VRAM",
                        "No CUDA GPU detected; CPU inference is too slow to offload real work.",
                        "Run a 7-14B coder locally → code-review/refactor/classification off the cloud."))
    elif vram < 12:
        tips.append(Tip("P2", "hardware", f"GPU has ~{vram:.0f} GB VRAM — consider ≥16 GB",
                        "Small VRAM caps you at tiny models; 16 GB fits a 14B-class coder.",
                        "Bigger local tier handles multi-file reasoning without cloud."))
    else:
        tips.append(Tip("P3", "hardware", f"GPU ({vram:.0f} GB) runs a 14B coder locally — good",
                        "Plenty for local coder/instruct models.",
                        "Keep the cloud only for the hardest reasoning/security tasks."))

    # --- vision acceleration ---
    if not _has_kind(backends, "comfyui"):
        tips.append(Tip("P2", "hardware", "Add a Hailo-8 / 8L / 10 NPU for vision",
                        "Vision (object detection, OCR, image/PDF understanding) is very token-heavy on cloud VLMs.",
                        "media_loader does detection/OCR locally at ~0 tokens before the LLM sees anything."))

    # --- Windows inference node ---
    if os_name.startswith("Windows") and _has_chat(backends):
        tips.append(Tip("P2", "infra", "Move the always-on inference node to Linux (or WSL2)",
                        "Forced Windows updates/reboots interrupt the local endpoint and add RAM/overhead; "
                        "a headless Linux server stays up and leaves more VRAM/RAM for the model.",
                        "Stable 24/7 local routing; fewer cloud fallbacks when the endpoint is down."))

    # --- vector store for caching ---
    if not _has_kind(backends, "qdrant"):
        tips.append(Tip("P2", "software", "Run Qdrant locally (:6333)",
                        "No vector store found; the semantic response cache and vector search need one.",
                        "-60% on repeated/similar queries (response_cache, vector_protocol)."))

    # --- dedicated shared inference host ---
    if len(snap.network_hosts) >= 2:
        tips.append(Tip("P3", "infra", "Dedicate the strongest host as a shared inference node",
                        f"{len(snap.network_hosts)} reachable hosts — running a model per machine wastes VRAM.",
                        "One model loaded once, all machines/projects point at it (set hosts in discovery)."))

    # --- cloud keys posture ---
    if _has_chat(backends) and not snap.cloud_keys:
        tips.append(Tip("P3", "software", "Optional: add ONE cloud key for hard escalations",
                        "No cloud key set — auto_router stays fully local, which is cheapest but caps hard tasks.",
                        "OPENROUTER_API_KEY unlocks DeepSeek/GLM/Grok only when local isn't enough."))

    # --- MCP wiring ---
    if not snap.mcp_wired:
        tips.append(Tip("P1", "mcp", "Wire the MCP server into this project",
                        "The agent here can't reach the local tools until .mcp.json registers botte-llm.",
                        "Run: python -m skills.bootstrap.cli .  → auto_route/local_chat/find_skills available."))

    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(tips, key=lambda t: order.get(t.priority, 9))


# ── ASCII cluster diagram ─────────────────────────────────────────────────────

def ascii_diagram(snap: Snapshot, width: int = 62) -> str:
    """Render the cluster as a fixed-width ASCII box (clean right border)."""
    hw = snap.hardware
    gpu = (hw.get("gpus") or ["no GPU"])[0]

    def row(text: str, indent: int = 1) -> str:
        body = (" " * indent + text)[:width].ljust(width)
        return f"│{body}│"

    title = " LOCAL CLUSTER "
    bar = title + "─" * (width - len(title))
    out = ["┌" + bar[:width] + "┐"]
    out.append(row(f"this machine · {hw.get('os','?')} · {hw.get('cpu_cores','?')} cores"))
    out.append(row(f"RAM {hw.get('ram_gb','?')}GB · GPU {gpu} ({hw.get('vram_gb',0)}GB VRAM)", indent=3))
    out.append(row(""))
    if snap.backends:
        out.append(row("reachable backends:"))
        for b in snap.backends:
            models = ", ".join(b.get("models", [])[:2])
            out.append(row(f"• {b.get('label','?')} {b.get('host')}:{b.get('port')}  [{models}]", indent=3))
    else:
        out.append(row("(no LLM backends discovered — see P0 tip)"))
    out.append(row(""))
    cloud = ", ".join(snap.cloud_keys) if snap.cloud_keys else "none (fully local)"
    out.append(row(f"cloud keys: {cloud}"))
    out.append(row(f"MCP wired here: {'yes' if snap.mcp_wired else 'no'}"))
    out.append("└" + "─" * width + "┘")
    if len(snap.network_hosts) >= 2:
        out.append("  network hosts: " + ", ".join(snap.network_hosts))
    return "\n".join(out)


def _score(tips: list[Tip]) -> int:
    score = 100
    weights = {"P0": 30, "P1": 15, "P2": 8, "P3": 2}
    for t in tips:
        score -= weights.get(t.priority, 0)
    return max(0, score)


def advise(project: Optional[Path] = None, scan_subnet: bool = False,
           fresh: bool = False) -> dict:
    snap = gather(project=project, scan_subnet=scan_subnet, fresh=fresh)
    tips = recommend(snap)
    return {
        "snapshot": asdict(snap),
        "diagram": ascii_diagram(snap),
        "tips": [t.to_dict() for t in tips],
        "infra_score": _score(tips),
    }
