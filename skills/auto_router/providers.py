"""Provider catalog — cloud LLMs the auto-router can reach, plus availability.

Everything here speaks the OpenAI `/v1/chat/completions` schema, so one client
covers all of them. Two ways to reach a cloud model:

  * OpenRouter  — one key (OPENROUTER_API_KEY), one endpoint, every model by slug.
  * Native      — the provider's own endpoint + its own key env var.

A model is *available* if a usable key is present (its native key, or
OPENROUTER_API_KEY when it has an OpenRouter slug). Local models are always
available when a backend is discovered (see skills.llm_backends).

The catalog is intentionally data-driven and conservative: model ids/versions
move fast, so treat slugs as defaults to edit, not gospel. Add a row, it routes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# Reuse the tier scale from the existing tiered router (no parallel enum).
from skills.tiered_router import Tier


OPENROUTER_BASE = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class CloudModel:
    key: str                 # short handle used in routing/CLI
    label: str               # human label
    tier: Tier               # capability/cost tier
    openrouter_slug: str = ""    # e.g. "deepseek/deepseek-chat"
    native_base_url: str = ""    # e.g. "https://api.deepseek.com/v1"
    native_model: str = ""       # model id at the native endpoint
    native_env: str = ""         # env var holding the native API key
    notes: str = ""


# Starter catalog — the models the user asked for, plus sensible tier-mates.
# Slugs/versions are editable defaults; bump them as providers release.
CATALOG: tuple[CloudModel, ...] = (
    # ── CHEAP tier — fast, cheap, good for review/extraction at scale ──
    CloudModel("gemma", "Google Gemma (cloud)", Tier.CHEAP,
               openrouter_slug="google/gemma-3-27b-it",
               notes="Gemma also runs LOCAL via Ollama/LM Studio — prefer local."),
    CloudModel("deepseek-chat", "DeepSeek V-series chat", Tier.CHEAP,
               openrouter_slug="deepseek/deepseek-chat",
               native_base_url="https://api.deepseek.com/v1",
               native_model="deepseek-chat", native_env="DEEPSEEK_API_KEY"),
    CloudModel("glm-air", "Zhipu GLM (air)", Tier.CHEAP,
               openrouter_slug="z-ai/glm-4.5-air",
               native_base_url="https://open.bigmodel.cn/api/paas/v4",
               native_model="glm-4.5-air", native_env="ZHIPUAI_API_KEY"),

    # ── STANDARD tier — solid reasoning / multi-file work ──
    CloudModel("glm", "Zhipu GLM", Tier.STANDARD,
               openrouter_slug="z-ai/glm-4.6",
               native_base_url="https://open.bigmodel.cn/api/paas/v4",
               native_model="glm-4.6", native_env="ZHIPUAI_API_KEY"),
    CloudModel("nemotron", "NVIDIA Nemotron", Tier.STANDARD,
               openrouter_slug="nvidia/llama-3.3-nemotron-super-49b-v1",
               native_base_url="https://integrate.api.nvidia.com/v1",
               native_model="nvidia/llama-3.3-nemotron-super-49b-v1",
               native_env="NVIDIA_API_KEY"),

    # ── PREMIUM tier — hardest reasoning, security, system design ──
    CloudModel("deepseek-reasoner", "DeepSeek Reasoner", Tier.PREMIUM,
               openrouter_slug="deepseek/deepseek-r1",
               native_base_url="https://api.deepseek.com/v1",
               native_model="deepseek-reasoner", native_env="DEEPSEEK_API_KEY"),
    CloudModel("grok", "xAI Grok", Tier.PREMIUM,
               openrouter_slug="x-ai/grok-4",
               native_base_url="https://api.x.ai/v1",
               native_model="grok-4", native_env="XAI_API_KEY"),
)


@dataclass
class ResolvedModel:
    """A cloud model resolved to a concrete callable endpoint + key."""
    key: str
    label: str
    tier: Tier
    base_url: str
    model: str
    api_key: str
    via: str            # "openrouter" | "native"

    def masked(self) -> dict:
        return {"key": self.key, "label": self.label, "tier": self.tier.name,
                "base_url": self.base_url, "model": self.model, "via": self.via}


def _openrouter_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")


def resolve(model: CloudModel) -> Optional[ResolvedModel]:
    """Resolve a catalog entry to a callable endpoint, or None if no key.

    Prefers a native key (direct, often cheaper); falls back to OpenRouter.
    """
    if model.native_env and os.environ.get(model.native_env):
        return ResolvedModel(
            key=model.key, label=model.label, tier=model.tier,
            base_url=model.native_base_url, model=model.native_model,
            api_key=os.environ[model.native_env], via="native",
        )
    if model.openrouter_slug and _openrouter_key():
        return ResolvedModel(
            key=model.key, label=model.label, tier=model.tier,
            base_url=OPENROUTER_BASE, model=model.openrouter_slug,
            api_key=_openrouter_key(), via="openrouter",
        )
    return None


def available_cloud(min_tier: Optional[Tier] = None) -> list[ResolvedModel]:
    """Resolved cloud models reachable right now (key present), tier-filtered."""
    out: list[ResolvedModel] = []
    for m in CATALOG:
        if min_tier is not None and m.tier < min_tier:
            continue
        r = resolve(m)
        if r:
            out.append(r)
    return sorted(out, key=lambda r: r.tier)


def cheapest_cloud_at_least(tier: Tier) -> Optional[ResolvedModel]:
    """Cheapest available cloud model whose tier is >= `tier`."""
    candidates = available_cloud(min_tier=tier)
    return candidates[0] if candidates else None


def catalog_overview() -> list[dict]:
    """Catalog with current availability — for `cli list` / audits."""
    rows = []
    for m in CATALOG:
        r = resolve(m)
        rows.append({
            "key": m.key, "label": m.label, "tier": m.tier.name,
            "available": r is not None,
            "via": r.via if r else None,
            "needs": (m.native_env or "OPENROUTER_API_KEY") if not r else None,
        })
    return rows
