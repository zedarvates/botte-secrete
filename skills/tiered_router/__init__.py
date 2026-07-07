"""Tiered Model Router (P14) — 5-level intelligent model selection.

Routes every LLM call through cost estimation and tier selection.
Auto-downgrades when budget exceeded. Tracks all usage.

Levels:
    L0 (0 tok, FREE):    Hailo-8, LocalAI TTS/STT, pure math, static analysis
    L1 (~100 tok, LOCAL): LocalAI Gemma-4, Ollama — simple Q&A, classification
    L2 (~500 tok, CHEAP): Cloud small — moderate analysis, code review
    L3 (~2K tok, STANDARD): Cloud standard — architecture, complex reasoning
    L4 (~8K tok, PREMIUM):  Cloud best — system design, security audit

Features:
    - Pre-call cost estimation (tokens + $)
    - Automatic downgrade on budget exceeded
    - Per-project budget limits
    - Usage tracking and reporting
    - Agent-to-agent compression (delta + shared KB)
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import IntEnum


# ── Tier Definitions ──

class Tier(IntEnum):
    """5-tier model selection with cost bounds."""
    FREE = 0       # 0 tokens, local hardware
    LOCAL = 1      # ~100 tokens, local LLM
    CHEAP = 2      # ~500 tokens, cloud small
    STANDARD = 3   # ~2K tokens, cloud standard
    PREMIUM = 4    # ~8K tokens, cloud best


# Tier characteristics: {tier: (max_tokens, est_cost_per_1k, description)}
TIER_INFO = {
    Tier.FREE:     (0, 0.0, "Local hardware — Hailo-8, ComfyUI, LocalAI"),
    Tier.LOCAL:    (100, 0.0, "Local LLM — Gemma-4 / Ollama"),
    Tier.CHEAP:    (500, 0.00015, "Cloud small — Haiku / Flash"),
    Tier.STANDARD: (2000, 0.001, "Cloud standard — Sonnet / GPT-4o-mini"),
    Tier.PREMIUM:  (8000, 0.015, "Cloud best — Opus / DeepSeek / GPT-4"),
}

# Task → tier mapping
TASK_TIER = {
    # Level 0 — FREE (no LLM)
    "vision_detect":     Tier.FREE,
    "vision_classify":   Tier.FREE,
    "vision_ocr":        Tier.FREE,
    "tts":               Tier.FREE,
    "stt":               Tier.FREE,
    "static_analysis":   Tier.FREE,
    "vector_search":     Tier.FREE,
    "fingerprint_check": Tier.FREE,
    "hash_compare":      Tier.FREE,

    # Level 1 — LOCAL
    "simple_qa":         Tier.LOCAL,
    "classification":    Tier.LOCAL,
    "summarize_short":   Tier.LOCAL,
    "template_fill":     Tier.LOCAL,
    "lint_suggestion":   Tier.LOCAL,
    "spell_check":       Tier.LOCAL,

    # Level 2 — CHEAP
    "code_review":       Tier.CHEAP,
    "bug_detect":        Tier.CHEAP,
    "refactor_suggest":  Tier.CHEAP,
    "doc_generate":      Tier.CHEAP,
    "test_generate":     Tier.CHEAP,

    # Level 3 — STANDARD
    "architecture":      Tier.STANDARD,
    "multi_file_analysis": Tier.STANDARD,
    "complex_reasoning": Tier.STANDARD,
    "audit_report":      Tier.STANDARD,
    "optimize_plan":     Tier.STANDARD,

    # Level 4 — PREMIUM
    "security_audit":    Tier.PREMIUM,
    "system_design":     Tier.PREMIUM,
    "critical_fix":      Tier.PREMIUM,
    "adversarial_review": Tier.PREMIUM,
}


# ── Cost Estimation ──

def estimate_tokens(task_type: str, input_size: int, complexity: float = 1.0) -> tuple[int, int]:
    """Estimate input + output tokens for a task.
    
    Args:
        task_type: Type of task (see TASK_TIER keys)
        input_size: Size of input in characters
        complexity: 0.5 = simple, 1.0 = normal, 2.0 = complex
    """
    # Rough char → token ratio: ~4 chars = 1 token
    input_tokens = max(1, int(input_size / 4))

    # Output estimation based on task type
    output_ratios = {
        "simple_qa": 0.5,
        "classification": 0.05,
        "summarize_short": 0.3,
        "code_review": 1.0,
        "bug_detect": 0.5,
        "refactor_suggest": 0.8,
        "architecture": 2.0,
        "audit_report": 1.5,
        "security_audit": 2.0,
    }
    ratio = output_ratios.get(task_type, 0.5)
    output_tokens = max(1, int(input_tokens * ratio * complexity))

    return input_tokens, output_tokens


def estimate_cost(tier: Tier, input_tokens: int, output_tokens: int) -> float:
    """Estimate $ cost for a tier.

    Bills the ACTUAL token counts, not clamped to the tier's nominal ceiling
    (TIER_INFO's max_tok describes what's *typical* for the tier, for tier
    selection — using it to cap the billing math silently under-counted cost
    for any call bigger than that ceiling, in both pre-call estimates and
    record()'s post-call budget tracking).
    """
    _, cost_per_1k, _ = TIER_INFO[tier]
    return ((input_tokens + output_tokens) / 1000) * cost_per_1k


# ── Budget Manager ──

@dataclass
class Budget:
    """Per-project budget limits."""
    daily: int = 50000       # Max tokens per day
    per_call: int = 8000     # Max tokens per call
    monthly_cost: float = 5.0  # Max $ per month
    
    used_today: int = 0
    used_this_month: float = 0.0
    calls_today: int = 0
    
    def can_afford(self, tier: Tier, input_tokens: int, output_tokens: int) -> bool:
        total = input_tokens + output_tokens
        cost = estimate_cost(tier, input_tokens, output_tokens)
        return (self.used_today + total <= self.daily and
                total <= self.per_call and
                self.used_this_month + cost <= self.monthly_cost)
    
    def spend(self, tier: Tier, input_tokens: int, output_tokens: int):
        self.used_today += input_tokens + output_tokens
        self.used_this_month += estimate_cost(tier, input_tokens, output_tokens)
        self.calls_today += 1


# ── Tiered Router ──

@dataclass
class CallRecord:
    """Record of a single LLM call."""
    task: str
    tier_requested: Tier
    tier_used: Tier
    input_tokens: int
    output_tokens: int
    cost: float
    downgraded: bool
    timestamp: float
    cache_hit: bool = False


class TieredRouter:
    """Intelligent model tier selection with budget awareness."""

    def __init__(self, budget: Optional[Budget] = None):
        self.budget = budget or Budget()
        self.history: list[CallRecord] = []
        self._cache: dict[str, Any] = {}

    def route(self, task_type: str, input_text: str,
              complexity: float = 1.0,
              force_tier: Optional[Tier] = None) -> dict:
        """Route a task to the appropriate tier.
        
        Returns:
            {
                "tier": Tier,
                "downgraded": bool,
                "est_input_tokens": int,
                "est_output_tokens": int,
                "est_cost": float,
                "reason": str,
                "local_available": bool,  # Can be served locally
            }
        """
        # Determine desired tier
        desired_tier = force_tier or TASK_TIER.get(task_type, Tier.STANDARD)
        in_tok, out_tok = estimate_tokens(task_type, len(input_text), complexity)
        cost = estimate_cost(desired_tier, in_tok, out_tok)

        # Check cache first
        cache_key = hashlib.sha256(
            f"{task_type}:{input_text}".encode()
        ).hexdigest()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if time.time() - entry["ts"] < 86400:  # 24h TTL
                return {
                    "tier": Tier.FREE, "downgraded": False,
                    "est_input_tokens": 0, "est_output_tokens": 0,
                    "est_cost": 0.0, "reason": "cache_hit",
                    "local_available": True, "cache_key": cache_key,
                }

        # Can we afford the desired tier?
        if not self.budget.can_afford(desired_tier, in_tok, out_tok):
            # Try downgrading
            downgraded = desired_tier
            for lower in reversed(range(desired_tier)):
                lower_tier = Tier(lower)
                if self.budget.can_afford(lower_tier, in_tok, out_tok):
                    in_tok2, out_tok2 = estimate_tokens(task_type, len(input_text), complexity)
                    cost2 = estimate_cost(lower_tier, in_tok2, out_tok2)
                    return {
                        "tier": lower_tier, "downgraded": True,
                        "original_tier": desired_tier,
                        "est_input_tokens": in_tok2, "est_output_tokens": out_tok2,
                        "est_cost": cost2,
                        "reason": f"Downgraded from {desired_tier.name} → {lower_tier.name} (budget)",
                        "local_available": lower_tier <= Tier.LOCAL,
                    }
            # Can't afford anything — use LOCAL as fallback
            return {
                "tier": Tier.LOCAL, "downgraded": True,
                "original_tier": desired_tier,
                "est_input_tokens": 100, "est_output_tokens": 50,
                "est_cost": 0.0,
                "reason": "Forced fallback — budget exhausted",
                "local_available": True,
            }

        # Check if local can handle it
        local_available = desired_tier <= Tier.LOCAL

        return {
            "tier": desired_tier, "downgraded": False,
            "est_input_tokens": in_tok, "est_output_tokens": out_tok,
            "est_cost": cost,
            "reason": f"Using {desired_tier.name} tier",
            "local_available": local_available,
        }

    def record(self, task: str, tier: Tier, in_tok: int, out_tok: int,
               downgraded: bool = False, cache_hit: bool = False):
        """Record a completed call."""
        cost = estimate_cost(tier, in_tok, out_tok)
        self.budget.spend(tier, in_tok, out_tok)
        self.history.append(CallRecord(
            task=task, tier_requested=TASK_TIER.get(task, Tier.STANDARD),
            tier_used=tier, input_tokens=in_tok, output_tokens=out_tok,
            cost=cost, downgraded=downgraded,
            timestamp=time.time(), cache_hit=cache_hit,
        ))

    def cache_response(self, cache_key: str, response: Any):
        self._cache[cache_key] = {"data": response, "ts": time.time()}
        # LRU eviction
        if len(self._cache) > 500:
            oldest = min(self._cache, key=lambda k: self._cache[k]["ts"])
            del self._cache[oldest]

    def report(self) -> dict:
        """Generate usage report."""
        if not self.history:
            return {"calls": 0, "message": "No calls recorded"}

        by_tier = {}
        total_tokens = 0
        total_cost = 0.0
        downgrades = 0
        cache_hits = 0

        for call in self.history:
            tier_name = call.tier_used.name
            if tier_name not in by_tier:
                by_tier[tier_name] = {"calls": 0, "tokens": 0, "cost": 0.0}
            by_tier[tier_name]["calls"] += 1
            by_tier[tier_name]["tokens"] += call.input_tokens + call.output_tokens
            by_tier[tier_name]["cost"] += call.cost
            total_tokens += call.input_tokens + call.output_tokens
            total_cost += call.cost
            if call.downgraded:
                downgrades += 1
            if call.cache_hit:
                cache_hits += 1

        # Estimate savings vs all-PREMIUM
        premium_cost = len(self.history) * 0.015  # rough estimate
        savings_pct = round((1 - total_cost / max(premium_cost, 0.001)) * 100)

        return {
            "calls": len(self.history),
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "savings_vs_premium_pct": savings_pct,
            "downgrades": downgrades,
            "cache_hits": cache_hits,
            "by_tier": by_tier,
            "budget": {
                "daily_used": self.budget.used_today,
                "daily_limit": self.budget.daily,
                "daily_pct": round(self.budget.used_today / max(self.budget.daily, 1) * 100),
                "monthly_cost": round(self.budget.used_this_month, 4),
                "monthly_limit": self.budget.monthly_cost,
            },
        }


# ── Agent-to-Agent Compression ──

class AgentCompressor:
    """Compress inter-agent communication using delta + shared knowledge base.
    
    Principle: Don't re-transmit what the other agent already knows.
    Agent B already has: project structure, core-agent.md, skill definitions.
    Only send: what CHANGED since last transmission.
    """

    def __init__(self):
        self.shared_kb: dict[str, Any] = {}  # Shared knowledge base
        self.transmission_history: list[dict] = []

    def add_to_kb(self, key: str, value: Any):
        """Add to shared knowledge — all agents can reference this."""
        self.shared_kb[key] = value

    def compress(self, data: dict, receiver_knows: Optional[set[str]] = None) -> dict:
        """Compress data for transmission to another agent.
        
        Only sends fields the receiver doesn't already have in shared_kb.
        Returns compact delta.
        """
        if receiver_knows is None:
            receiver_knows = set(self.shared_kb.keys())

        compressed = {}
        for key, value in data.items():
            if key in receiver_knows and self.shared_kb.get(key) == value:
                continue  # Already known — skip
            if isinstance(value, dict):
                sub = self.compress(value, receiver_knows)
                if sub:
                    compressed[key] = sub
            elif isinstance(value, list):
                # For lists, only send new items (by hash)
                if key in receiver_knows:
                    known_hashes = set()
                    if isinstance(self.shared_kb.get(key), list):
                        known_hashes = {
                            hashlib.sha256(
                                json.dumps(item, sort_keys=True).encode()
                            ).hexdigest()
                            for item in self.shared_kb[key]
                        }
                    new_items = []
                    for item in value:
                        item_hash = hashlib.sha256(
                            json.dumps(item, sort_keys=True).encode()
                        ).hexdigest()
                        if item_hash not in known_hashes:
                            new_items.append(item)
                    if new_items:
                        compressed[key] = new_items
                else:
                    compressed[key] = value
            else:
                if key not in receiver_knows or self.shared_kb.get(key) != value:
                    compressed[key] = value

        self.transmission_history.append({
            "original_size": len(json.dumps(data)),
            "compressed_size": len(json.dumps(compressed)),
            "fields_sent": list(compressed.keys()),
            "time": time.time(),
        })

        return compressed

    def decompress(self, compressed: dict, existing: dict) -> dict:
        """Merge compressed delta into existing data."""
        result = {**existing}
        for key, value in compressed.items():
            if isinstance(value, dict) and key in result:
                result[key] = self.decompress(value, result[key])
            else:
                result[key] = value
        return result

    def savings_report(self) -> dict:
        if not self.transmission_history:
            return {"message": "No transmissions yet"}

        original_total = sum(t["original_size"] for t in self.transmission_history)
        compressed_total = sum(t["compressed_size"] for t in self.transmission_history)
        return {
            "transmissions": len(self.transmission_history),
            "original_chars": original_total,
            "compressed_chars": compressed_total,
            "savings_pct": round((1 - compressed_total / max(original_total, 1)) * 100),
        }


# ── Demo ──

if __name__ == "__main__":
    print("=== Tiered Model Router (P14) ===\n")

    router = TieredRouter()

    # Test routing
    tasks = [
        ("simple_qa", "Qu'est-ce que le pattern Singleton ?", 0.5),
        ("code_review", "def f(x): return x*2 # review this", 1.0),
        ("security_audit", "Full authentication system design with JWT...", 2.0),
        ("vision_detect", "/tmp/photo.jpg", 1.0),
        ("complex_reasoning", "Design a distributed cache with consistency...", 1.5),
    ]

    for task, input_str, complexity in tasks:
        result = router.route(task, input_str, complexity)
        tier_name = result["tier"].name
        icon = "🟢" if result["local_available"] else "🔵" if tier_name in ("CHEAP",) else "🟡" if tier_name == "STANDARD" else "🔴"
        downgrade = " ⬇️" if result.get("downgraded") else ""
        print(f"{icon} {task:25s} → {tier_name:10s}{downgrade} ({result['est_input_tokens']}+{result['est_output_tokens']} tok, ${result['est_cost']:.6f})")
        router.record(task, result["tier"], result["est_input_tokens"], result["est_output_tokens"],
                     downgraded=result.get("downgraded", False))

    rep = router.report()
    print(f"\n📊 Usage: {rep['calls']} calls, {rep['total_tokens']:,} tokens, ${rep['total_cost']:.6f}")
    print(f"💰 Savings vs all-PREMIUM: {rep['savings_vs_premium_pct']}%")
    print(f"📉 Downgrades: {rep['downgrades']}, ♻️ Cache hits: {rep['cache_hits']}")
    print(f"📊 Budget: {rep['budget']['daily_pct']}% daily used")
    for tier_name, stats in rep["by_tier"].items():
        print(f"  {tier_name}: {stats['calls']} calls, {stats['tokens']:,} tok, ${stats['cost']:.6f}")

    # Agent-to-Agent Compression
    print("\n=== Agent-to-Agent Compression ===\n")
    compressor = AgentCompressor()
    compressor.add_to_kb("project_root", "/home/redgamer/projects/turboquant")
    compressor.add_to_kb("language", "python")
    compressor.add_to_kb("framework", "ccxt")

    # Porthos sends audit report
    audit = {
        "project_root": "/home/redgamer/projects/turboquant",
        "language": "python",
        "health": 72,
        "findings": [
            {"file": "core.py:42", "type": "dead", "desc": "unused calc_tax()"},
            {"file": "auth.py:30", "type": "sec", "desc": "API_KEY exposed"},
        ],
        "new_field": "only this is new",
    }

    compressed = compressor.compress(audit)
    print(f"Original:  {len(json.dumps(audit))} chars")
    print(f"Compressed: {len(json.dumps(compressed))} chars")
    print(f"Savings: {compressor.savings_report()['savings_pct']}%")
    print(f"Sent fields: {list(compressed.keys())}")
    print(f"  (skipped: project_root, language — already in shared KB)")
