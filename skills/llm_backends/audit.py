"""Local LLM Audit — does this setup use local models, and what *could* it run?

Two jobs:
  1. Detect whether any local backend is reachable (via the registry/discovery).
  2. Profile the host hardware (RAM, CPU, GPU/VRAM, OS) and recommend a concrete,
     adaptive setup: which server to install, which model size fits, and which
     model to prefer per project type.

Used by the onboarding companion: if no local model is in use, we don't just say
"install something" — we tell the user *exactly* what their machine can run.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional

from skills.llm_backends import registry
from skills.llm_backends.discovery import Backend


# ── Hardware profile ─────────────────────────────────────────────────────────

@dataclass
class Hardware:
    os: str
    arch: str
    cpu_cores: int
    ram_gb: float
    gpus: list[str] = field(default_factory=list)
    vram_gb: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _total_ram_gb() -> float:
    """Total physical RAM in GB, best-effort across platforms (stdlib only)."""
    # Linux / macOS: sysconf
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / (1024 ** 3), 1)
    except (ValueError, AttributeError, OSError):
        pass
    # Windows: GlobalMemoryStatusEx via ctypes
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except (ImportError, OSError, AttributeError):
        return 0.0


def _detect_gpus() -> tuple[list[str], float]:
    """Return (gpu names, total VRAM GB). Best-effort via nvidia-smi, else empty."""
    gpus: list[str] = []
    vram_mb_total = 0.0

    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout.strip()
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gpus.append(parts[0])
                    try:
                        vram_mb_total += float(parts[1])
                    except ValueError:
                        pass
        except (OSError, subprocess.SubprocessError):
            pass

    # Windows fallback: list GPU names via WMIC (no VRAM reliably).
    if not gpus and platform.system() == "Windows" and shutil.which("wmic"):
        try:
            out = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout
            gpus = [l.strip() for l in out.splitlines()[1:] if l.strip()]
        except (OSError, subprocess.SubprocessError):
            pass

    return gpus, round(vram_mb_total / 1024, 1)


def profile_hardware() -> Hardware:
    gpus, vram = _detect_gpus()
    return Hardware(
        os=f"{platform.system()} {platform.release()}",
        arch=platform.machine(),
        cpu_cores=os.cpu_count() or 1,
        ram_gb=_total_ram_gb(),
        gpus=gpus,
        vram_gb=vram,
    )


# ── Model-size recommendation ────────────────────────────────────────────────

# (max_budget_gb, model id, label) — budget = VRAM if present, else RAM.
MODEL_TIERS = [
    (3.0,  "qwen2.5:0.5b",   "Tiny — classification, routing, spell-check"),
    (6.0,  "llama3.2:3b",    "Small — Q&A, summaries, simple code hints"),
    (10.0, "qwen2.5:7b",     "Medium — code review, refactor suggestions"),
    (18.0, "qwen2.5-coder:14b", "Large — multi-file code reasoning"),
    (32.0, "qwen2.5:32b",    "XL — architecture, complex reasoning"),
    (9_999.0, "qwen2.5:72b", "XXL — premium-class local reasoning"),
]


def recommend_model(hw: Hardware) -> dict:
    """Pick the biggest model that fits the available memory budget."""
    budget = hw.vram_gb if hw.vram_gb >= 2 else hw.ram_gb * 0.6  # leave headroom
    chosen = MODEL_TIERS[0]
    for tier in MODEL_TIERS:
        if budget >= tier[0]:
            chosen = tier
    return {
        "budget_gb": round(budget, 1),
        "basis": "VRAM" if hw.vram_gb >= 2 else "RAM (60%)",
        "model": chosen[1],
        "tier": chosen[2],
    }


# Preferred local model per project type (matches skill_project_optimizer types).
PROJECT_MODEL_HINTS = {
    "web-frontend":  "qwen2.5-coder",
    "web-backend":   "qwen2.5-coder",
    "cli":           "qwen2.5-coder",
    "ml":            "qwen2.5",
    "data":          "qwen2.5",
    "infra":         "qwen2.5",
    "docs":          "llama3.2",
    "unknown":       "qwen2.5",
}


# ── Full audit ───────────────────────────────────────────────────────────────

def audit(hosts: Optional[list[str]] = None, scan_subnet: bool = False,
          fresh: bool = False) -> dict:
    """Audit local-LLM usage and produce setup recommendations.

    If `fresh`, runs discovery now; otherwise reads the saved registry.
    """
    if fresh:
        backends = registry.refresh(hosts=hosts, scan_subnet=scan_subnet)
    else:
        backends = registry.load() or registry.refresh(hosts=hosts,
                                                        scan_subnet=scan_subnet)

    hw = profile_hardware()
    chat = registry.chat_backends(backends)
    uses_local = len(chat) > 0
    rec = recommend_model(hw)

    steps: list[str] = []
    if not uses_local:
        # Onboarding path — concrete, machine-aware.
        if hw.vram_gb >= 6 or hw.ram_gb >= 16:
            steps = [
                "1. Install LM Studio (https://lmstudio.ai) — easiest GUI, "
                "OpenAI-compatible server on port 1234.",
                f"2. Download a model that fits your hardware: {rec['model']} "
                f"({rec['tier']}, ~{rec['budget_gb']} GB {rec['basis']} budget).",
                "3. In LM Studio → Developer tab → Start Server (port 1234).",
                "4. Re-run `python -m skills.llm_backends.cli scan` to register it.",
                "5. Point the routers at it: they read configs/llm-endpoints.json "
                "automatically.",
            ]
        else:
            steps = [
                "1. Your machine is memory-light — install Ollama "
                "(https://ollama.com) and pull a tiny model: `ollama pull "
                f"{rec['model']}`.",
                "2. Ollama serves OpenAI-compatible API on port 11434 by default.",
                "3. Re-run `python -m skills.llm_backends.cli scan`.",
                "4. Offload only classification / routing / short summaries locally; "
                "keep complex reasoning on the cloud.",
            ]
    else:
        steps = [
            f"✅ {len(chat)} local chat backend(s) detected — local routing is active.",
            "Tune per project with `python -m skills.llm_backends.cli profile <project>`.",
        ]

    return {
        "uses_local_models": uses_local,
        "hardware": hw.to_dict(),
        "recommended_model": rec,
        "project_model_hints": PROJECT_MODEL_HINTS,
        "backends": [b.to_dict() for b in backends],
        "chat_backends": [f"{b.label} {b.host}:{b.port}" for b in chat],
        "next_steps": steps,
    }


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(audit(fresh="--fresh" in sys.argv), indent=2, ensure_ascii=False))
