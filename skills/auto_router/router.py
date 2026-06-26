"""AutoRouter — auto-decide local vs cloud and pick a concrete model.

Pipeline per task:
    estimate effort → target tier
    tier ≤ LOCAL and a local backend exists → run LOCAL (0 cloud tokens)
    else → cheapest available CLOUD model at/above the tier
    budget-aware: downgrade a step when the cloud spend would breach the budget
    nothing available at tier → fall back to local, else report

A single unified client calls either side (both speak OpenAI /v1/chat).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from skills.tiered_router import Tier, TIER_INFO, Budget, estimate_tokens, estimate_cost
from skills.auto_router.effort import estimate as estimate_effort, EffortEstimate
from skills.auto_router import providers
from skills.auto_router import nn_belt
from skills.llm_backends import registry
from skills.llm_backends.client import LocalLLMClient, LocalLLMError, ChatResult


@dataclass
class AutoDecision:
    mode: str                  # "local" | "cloud" | "none"
    tier: Tier
    effort: EffortEstimate
    model: str = ""
    label: str = ""
    base_url: str = ""
    via: str = ""              # local | native | openrouter
    reason: str = ""
    est_cost: float = 0.0
    _api_key: str = field(default="", repr=False)
    # binary_router features + predicted class when the NN belt drove this decision,
    # so the outcome can be logged back as implicit feedback (None = belt didn't act).
    _belt_ctx: Optional[dict] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "tier": self.tier.name,
                "effort": self.effort.to_dict(), "model": self.model,
                "label": self.label, "via": self.via, "reason": self.reason,
                "est_cost": round(self.est_cost, 6)}


class AutoRouter:
    def __init__(self, budget: Optional[Budget] = None):
        self.budget = budget or Budget()

    # ── decision ──
    def decide(self, prompt: str, task_type: str = "",
               force_tier: Optional[Tier] = None) -> AutoDecision:
        eff = estimate_effort(prompt, task_type=task_type)
        tier = force_tier or eff.tier

        local = registry.best_chat_backend()
        local_model = registry.preferred_model(local) if local else None

        # ── NN belt: a learned second opinion on local-vs-cloud (0 cloud tokens,
        # abstains when unsure). Conservative v1 — only pull a *borderline* task
        # (LOCAL < tier ≤ CHEAP) toward local when binary_router is confident and
        # a local backend exists. Hard tasks (STANDARD/PREMIUM) and forced tiers
        # are never touched, so the belt can save tokens but not raise cost/risk.
        if local and force_tier is None and Tier.LOCAL < tier <= Tier.CHEAP:
            budget_ratio = max(0.0, 1.0 - self.budget.used_today / max(self.budget.daily, 1))
            hint = nn_belt.local_vs_cloud_hint(eff.score, budget_ratio, has_local=True)
            if hint and hint[0] == "local":
                return AutoDecision(
                    mode="local", tier=Tier.LOCAL, effort=eff,
                    model=local_model or "local-model",
                    label=f"{local.label} {local.host}:{local.port}",
                    base_url=local.base_url, via="local",
                    reason=f"effort {eff.score:.2f}→{tier.name}; NN belt → local "
                           f"(conf {hint[1]:.2f}, 0 cloud tokens)",
                    _belt_ctx={"features": nn_belt.featurize_binary_router(
                                   eff.score, budget_ratio, True),
                               "predicted_class": 0},  # 0 = local
                )

        # Local handles FREE/LOCAL outright, and is the preferred fallback.
        if tier <= Tier.LOCAL and local:
            return AutoDecision(
                mode="local", tier=tier, effort=eff,
                model=local_model or "local-model",
                label=f"{local.label} {local.host}:{local.port}",
                base_url=local.base_url, via="local",
                reason=f"effort {eff.score:.2f}→{tier.name}; local backend covers it",
            )

        # Cloud path — cheapest available model at/above the tier, budget-aware.
        in_tok, out_tok = estimate_tokens(task_type or "code_review", len(prompt))
        chosen_tier = tier
        while chosen_tier >= Tier.CHEAP:
            cloud = providers.cheapest_cloud_at_least(chosen_tier)
            if cloud:
                cost = estimate_cost(cloud.tier, in_tok, out_tok)
                if self.budget.can_afford(cloud.tier, in_tok, out_tok):
                    note = "" if chosen_tier == tier else f" (downgraded from {tier.name})"
                    return AutoDecision(
                        mode="cloud", tier=cloud.tier, effort=eff,
                        model=cloud.model, label=cloud.label,
                        base_url=cloud.base_url, via=cloud.via,
                        reason=f"effort {eff.score:.2f}→{tier.name}; cloud {cloud.label}{note}",
                        est_cost=cost, _api_key=cloud.api_key,
                    )
            chosen_tier = Tier(chosen_tier - 1)  # try a cheaper tier

        # No affordable/available cloud — fall back to local if we have it.
        if local:
            return AutoDecision(
                mode="local", tier=Tier.LOCAL, effort=eff,
                model=local_model or "local-model",
                label=f"{local.label} {local.host}:{local.port}",
                base_url=local.base_url, via="local",
                reason=f"effort {eff.score:.2f}→{tier.name}, but no affordable cloud → local fallback",
            )
        return AutoDecision(mode="none", tier=tier, effort=eff,
                            reason="No local backend and no cloud key available")

    # ── execution (unified client) ──
    def run(self, prompt: str, *, task_type: str = "", system: Optional[str] = None,
            max_tokens: int = 1024, force_tier: Optional[Tier] = None) -> dict:
        d = self.decide(prompt, task_type=task_type, force_tier=force_tier)
        if d.mode == "none":
            return {"decision": d.to_dict(), "error": d.reason}
        if d.mode == "local":
            try:
                res = LocalLLMClient().chat(prompt, system=system, model=d.model,
                                            max_tokens=max_tokens)
                text, usage = res.text, res.total_tokens
            except LocalLLMError as e:
                # The belt routed local and local failed → strong implicit feedback
                # that this should have been cloud. Label it for the loop.
                self._log_feedback(d, actual_class=1)  # 1 = cloud
                return {"decision": d.to_dict(), "error": str(e)}
            else:
                # Local handled it → tentative positive label for binary_router.
                self._log_feedback(d, actual_class=0)  # 0 = local
        else:
            text, usage = _cloud_chat(d, prompt, system, max_tokens)
            self.budget.spend(d.tier, usage // 2 or 1, usage // 2 or 1)
        # feed the control loop (best-effort; never affects routing)
        try:
            from skills.control_loop.control_loop import record
            record(task=task_type or prompt, effort_score=d.effort.score,
                   tier=d.tier.name, mode=d.mode,
                   tokens_saved=(usage if d.mode == "local" else 0),
                   escalated="fallback" in d.reason or d.mode == "cloud",
                   success=bool(text))
        except Exception:
            pass
        return {"decision": d.to_dict(), "text": text, "tokens": usage}

    @staticmethod
    def _log_feedback(d: AutoDecision, actual_class: int) -> None:
        """Best-effort: record the belt's prediction + the real outcome for learning."""
        ctx = d._belt_ctx
        if not ctx:
            return
        try:
            from skills.botte_nn.active_learning import record_feedback
            record_feedback("binary_router", ctx["features"],
                            ctx["predicted_class"], actual_class)
        except Exception:
            pass

    def record_override(self, decision: AutoDecision, should_have_been: str) -> bool:
        """Log explicit feedback that the belt's local/cloud choice was overridden.

        `should_have_been` is 'local' or 'cloud'. Returns True iff the belt actually
        drove the decision (else there is nothing to correct). This is the strong
        ground-truth signal: a human/agent forcing the other route = a real label.
        """
        if not decision._belt_ctx:
            return False
        self._log_feedback(decision, 0 if should_have_been == "local" else 1)
        return True


def _cloud_chat(d: AutoDecision, prompt: str, system: Optional[str],
                max_tokens: int) -> tuple[str, int]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({"model": d.model, "messages": messages,
                       "temperature": 0.2, "max_tokens": max_tokens,
                       "stream": False}).encode()
    req = urllib.request.Request(
        d.base_url.rstrip("/") + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {d._api_key}",
                 "HTTP-Referer": "https://github.com/zedarvates/botte-secrete",
                 "X-Title": "botte-secrete"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"cloud call to {d.label} failed: {e}")
    msg = payload["choices"][0]["message"]
    text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    usage = payload.get("usage", {}) or {}
    total = int(usage.get("total_tokens", 0)) or (len(text) // 4)
    return text, total


# Convenience
_router = AutoRouter()


def auto_route(prompt: str, task_type: str = "") -> dict:
    """Decision only (no call). `auto_route('classify: bug or feature?')`."""
    return _router.decide(prompt, task_type=task_type).to_dict()


def auto_run(prompt: str, **kwargs) -> dict:
    """Decide + execute on the chosen backend."""
    return _router.run(prompt, **kwargs)
