"""Fusion — make several models collaborate instead of trusting one.

Three strategies, all built on the unified clients:

  cascade       run the cheap/local model first; escalate to a stronger one only
                if the answer looks low-confidence. (effort compounds upward)
  draft_refine  local model drafts; a stronger model refines. This is the
                "local + cloud together" mode — local does the bulk for free,
                the expensive model only polishes.
  vote          ask several models the same thing, return the consensus answer.
                Great for classification / short factual calls.

Everything degrades gracefully: with no cloud key, cascade/refine just use the
best local model, and vote runs over whatever backends exist.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Callable, Optional

from skills.tiered_router import Tier
from skills.auto_router.router import AutoRouter, _cloud_chat, AutoDecision
from skills.auto_router import providers
from skills.llm_backends import registry
from skills.llm_backends.client import LocalLLMClient, LocalLLMError


_UNCERTAIN = ("i'm not sure", "i am not sure", "cannot determine", "unclear",
              "not enough information", "as an ai", "i don't know", "je ne sais pas")


def _looks_confident(text: str) -> bool:
    if not text or len(text.strip()) < 2:
        return False
    low = text.lower()
    return not any(p in low for p in _UNCERTAIN)


def _run_local(prompt: str, system: Optional[str], max_tokens: int) -> str:
    try:
        return LocalLLMClient().chat(prompt, system=system, max_tokens=max_tokens).text
    except LocalLLMError:
        return ""


def _run_cloud(model_key_tier: Tier, prompt: str, system: Optional[str],
               max_tokens: int) -> tuple[str, str]:
    """Run on the cheapest available cloud model at/above a tier. Returns (text,label)."""
    cloud = providers.cheapest_cloud_at_least(model_key_tier)
    if not cloud:
        return "", ""
    d = AutoDecision(mode="cloud", tier=cloud.tier, effort=None,  # type: ignore
                     model=cloud.model, label=cloud.label, base_url=cloud.base_url,
                     via=cloud.via, _api_key=cloud.api_key)
    try:
        text, _ = _cloud_chat(d, prompt, system, max_tokens)
        return text, cloud.label
    except RuntimeError:
        return "", ""


# ── strategies ────────────────────────────────────────────────────────────────

def cascade(prompt: str, *, task_type: str = "", max_tokens: int = 512,
            confidence: Callable[[str], bool] = _looks_confident) -> dict:
    """Cheap-first; escalate one tier if the answer looks low-confidence."""
    router = AutoRouter()
    steps = []

    first = router.run(prompt, task_type=task_type, max_tokens=max_tokens)
    text = first.get("text", "")
    steps.append({"stage": "primary", "backend": first["decision"]["label"],
                  "confident": confidence(text)})
    if confidence(text):
        return {"strategy": "cascade", "answer": text, "escalated": False, "steps": steps}

    # Escalate: force a higher tier (prefer cloud STANDARD+).
    text2, label = _run_cloud(Tier.STANDARD, prompt, None, max_tokens)
    if text2:
        steps.append({"stage": "escalation", "backend": label, "confident": confidence(text2)})
        return {"strategy": "cascade", "answer": text2, "escalated": True, "steps": steps}

    # No cloud to escalate to — return the best local attempt.
    return {"strategy": "cascade", "answer": text, "escalated": False,
            "steps": steps, "note": "no stronger backend available to escalate"}


def draft_refine(prompt: str, *, max_tokens: int = 1024,
                 refine_tier: Tier = Tier.STANDARD) -> dict:
    """Local model drafts; a stronger model refines. Local does the heavy lifting."""
    draft = _run_local(f"Draft a first answer (it will be refined):\n\n{prompt}",
                       None, max_tokens)
    if not draft:
        # No local — just go straight to cloud.
        text, label = _run_cloud(refine_tier, prompt, None, max_tokens)
        return {"strategy": "draft_refine", "draft": "", "answer": text,
                "refined_by": label or "none", "note": "no local backend; cloud only"}

    refine_prompt = (
        "Improve the following draft answer: fix errors, tighten it, keep it "
        f"correct and complete.\n\n## Question\n{prompt}\n\n## Draft\n{draft}\n\n"
        "## Improved answer")
    refined, label = _run_cloud(refine_tier, refine_prompt, None, max_tokens)
    if refined:
        return {"strategy": "draft_refine", "draft": draft, "answer": refined,
                "refined_by": label, "drafted_locally": True}
    return {"strategy": "draft_refine", "draft": draft, "answer": draft,
            "refined_by": "none (no cloud key)", "drafted_locally": True}


def _normalize(ans: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", ans.lower()).strip()[:60]


def vote(prompt: str, *, max_tokens: int = 64, include_local: bool = True) -> dict:
    """Ask every reachable backend the same thing; return the consensus."""
    ballots: list[dict] = []

    if include_local and registry.best_chat_backend():
        t = _run_local(prompt, None, max_tokens)
        if t:
            ballots.append({"backend": "local", "answer": t.strip()})

    for cloud in providers.available_cloud(min_tier=Tier.CHEAP):
        d = AutoDecision(mode="cloud", tier=cloud.tier, effort=None,  # type: ignore
                         model=cloud.model, label=cloud.label, base_url=cloud.base_url,
                         via=cloud.via, _api_key=cloud.api_key)
        try:
            t, _ = _cloud_chat(d, prompt, None, max_tokens)
            if t:
                ballots.append({"backend": cloud.label, "answer": t.strip()})
        except RuntimeError:
            continue

    if not ballots:
        return {"strategy": "vote", "answer": "", "votes": 0,
                "note": "no backends reachable"}

    tally = Counter(_normalize(b["answer"]) for b in ballots)
    winner_norm, count = tally.most_common(1)[0]
    winner = next(b["answer"] for b in ballots if _normalize(b["answer"]) == winner_norm)
    return {"strategy": "vote", "answer": winner, "votes": count,
            "total": len(ballots), "agreement": round(count / len(ballots), 2),
            "ballots": ballots}
