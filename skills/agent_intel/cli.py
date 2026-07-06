"""Agent Intelligence — 6 optimisations avancées Copilot (P64-P69).

P64 — Loop Distillation: distiller les boucles réussies dans micro-NN
P65 — Skill-Level RAG: ne charger que les skills nécessaires
P66 — Predictive Fix Planning: prédire coût/utilité des corrections
P67 — Agent Memory Compression: compresser les mémoires agents
P68 — Predictive Routing: prédire le meilleur chemin avant exécution
P69 — Agent Knowledge Distillation: distiller entre agents

Usage:
    python -m skills.agent_intel.cli loop-distill --success "fix bug" --tokens 1500
    python -m skills.agent_intel.cli skill-rag "security audit" --skills scanner,fixer
    python -m skills.agent_intel.cli predict-fix "vuln in auth" --budget 2000
    python -m skills.agent_intel.cli mem-compress "agent memory text"
    python -m skills.agent_intel.cli predict-route "fix vuln" --agents scanner,fixer,reporter
    python -m skills.agent_intel.cli distill --from fixer --to scanner "correction pattern"
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

STORE = Path.home() / ".botte" / "agent-intel.json"


# ── Shared state ──────────────────────────────────────────────

class AgentIntel:
    """Stocke et analyse les données d'intelligence agents."""

    def __init__(self):
        self.loops: list[dict] = []
        self.skills: dict[str, dict] = {}
        self.fixes: list[dict] = []
        self.memories: dict[str, list[str]] = defaultdict(list)
        self.knowledge: dict[str, list[str]] = defaultdict(list)
        self._load()

    def _load(self):
        if STORE.exists():
            try:
                data = json.loads(STORE.read_text())
                self.loops = data.get("loops", [])
                self.skills = data.get("skills", {})
                self.fixes = data.get("fixes", [])
                self.knowledge = defaultdict(list, data.get("knowledge", {}))
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps({
            "loops": self.loops[-500:],  # Keep last 500
            "skills": self.skills,
            "fixes": self.fixes[-500:],
            "knowledge": dict(self.knowledge),
        }, indent=2))

    # ── P64: Loop Distillation ─────────────────────────────

    def record_loop(self, description: str, tokens_used: int,
                    success: bool, agent: str = ""):
        """Record a retroactive loop for distillation."""
        self.loops.append({
            "description": description[:100],
            "tokens": tokens_used,
            "success": success,
            "agent": agent,
            "hash": hashlib.sha256(description.encode()).hexdigest()[:12],
        })
        self._save()

    def loop_stats(self) -> dict:
        """Analyze loops to find patterns for distillation."""
        if not self.loops:
            return {"total_loops": 0}

        total = len(self.loops)
        successes = sum(1 for l in self.loops if l["success"])
        total_tokens = sum(l["tokens"] for l in self.loops)
        wasted = sum(l["tokens"] for l in self.loops if not l["success"])

        # Find repeated patterns (same hash → should be cached)
        hashes = Counter(l["hash"] for l in self.loops)
        repeatable = sum(c - 1 for c in hashes.values() if c > 1)
        repeatable_tokens = repeatable * (total_tokens // max(total, 1))

        return {
            "total_loops": total,
            "success_rate": round(successes / total * 100, 1),
            "total_tokens": total_tokens,
            "wasted_tokens": wasted,
            "wasted_pct": round(wasted / max(total_tokens, 1) * 100, 1),
            "repeatable_loops": repeatable,
            "estimated_savings_distill": repeatable_tokens,
            "by_agent": dict(Counter(l["agent"] for l in self.loops if l["agent"])),
        }

    # ── P65: Skill-Level RAG ───────────────────────────────

    def register_skill(self, name: str, tokens: int = 1000,
                       domain: str = "generic", keywords: str = ""):
        """Register a skill with its token cost and domain."""
        self.skills[name] = {
            "tokens": tokens, "domain": domain,
            "keywords": keywords.split(",") if keywords else [],
            "uses": 0,
        }
        self._save()

    def select_skills(self, task: str, budget: int = 4000) -> list[dict]:
        """Select only the skills needed for a task, within budget."""
        task_lower = task.lower()
        scored = []

        for name, info in self.skills.items():
            relevance = sum(1 for kw in info["keywords"]
                          if kw.strip().lower() in task_lower)
            relevance /= max(len(info["keywords"]), 1)
            scored.append((relevance, name, info))

        scored.sort(key=lambda x: -x[0])

        selected = []
        total_tokens = 0
        for relevance, name, info in scored:
            if relevance == 0 and len(selected) >= 3:
                continue
            if total_tokens + info["tokens"] <= budget:
                selected.append({"name": name, "relevance": relevance,
                                "tokens": info["tokens"]})
                total_tokens += info["tokens"]
                self.skills[name]["uses"] = self.skills[name].get("uses", 0) + 1

        self._save()
        return selected

    # ── P66: Predictive Fix Planning ────────────────────────

    def predict_fix(self, issue: str, budget: int = 2000) -> dict:
        """Predict if a fix is worth doing and estimate cost."""
        issue_lower = issue.lower()

        # Keywords-based estimation
        complexity = 0.5
        if any(w in issue_lower for w in ["security", "vuln", "cve", "exploit"]):
            complexity = 0.8
        elif any(w in issue_lower for w in ["bug", "error", "crash", "fail"]):
            complexity = 0.6
        elif any(w in issue_lower for w in ["typo", "format", "style"]):
            complexity = 0.2

        estimated_tokens = int(budget * complexity)
        worth_it = estimated_tokens <= budget

        # Check history
        similar = [f for f in self.fixes
                  if any(w in f.get("issue", "") for w in issue_lower.split()[:3])]
        avg_previous_cost = sum(f.get("tokens", 0) for f in similar) // max(len(similar), 1)

        return {
            "issue": issue[:60],
            "complexity": complexity,
            "estimated_tokens": estimated_tokens,
            "budget": budget,
            "worth_it": worth_it,
            "similar_past_fixes": len(similar),
            "avg_past_cost": avg_previous_cost,
            "recommendation": "fix now" if worth_it else "defer or skip",
        }

    def record_fix(self, issue: str, tokens: int, success: bool):
        """Record a fix for future planning."""
        self.fixes.append({
            "issue": issue[:100],
            "tokens": tokens,
            "success": success,
        })
        self._save()

    # ── P67: Agent Memory Compression ───────────────────────

    def compress_memory(self, agent: str, memory: str,
                        max_tokens: int = 500) -> str:
        """Compress an agent's memory by clustering and dedup."""
        lines = memory.split("\n")
        # Dedup consecutive similar lines
        compressed = []
        prev = ""
        for line in lines:
            if line != prev:
                compressed.append(line)
            prev = line

        # Cluster by topic (crude: first word as topic)
        topics = defaultdict(list)
        for line in compressed:
            topic = line.split()[0] if line.strip() else "other"
            topics[topic].append(line)

        # Build compressed memory
        result = []
        total_tok = 0
        for topic, lines in sorted(topics.items()):
            header = f"[{topic}: {len(lines)} entries]"
            result.append(header)
            total_tok += len(header) // 4
            for line in lines[:3]:  # Max 3 per topic
                if total_tok < max_tokens:
                    result.append(line)
                    total_tok += len(line) // 4

        compressed_text = "\n".join(result)

        # Store
        self.memories[agent].append(compressed_text)
        self._save()

        return compressed_text

    # ── P68: Predictive Routing ─────────────────────────────

    def predict_route(self, task: str, agents: list[str]) -> list[str]:
        """Predict the optimal agent path before execution."""
        task_lower = task.lower()

        # Score each agent's relevance
        agent_scores = []
        for agent in agents:
            score = 0.0
            if "security" in task_lower and agent in ["scanner", "audit"]:
                score = 0.9
            elif "fix" in task_lower and agent in ["fixer", "optimizer"]:
                score = 0.8
            elif "test" in task_lower and agent in ["tester", "verifier"]:
                score = 0.8
            elif "deploy" in task_lower and agent in ["builder", "deployer"]:
                score = 0.9
            elif "doc" in task_lower and agent in ["writer", "docgen"]:
                score = 0.7
            elif agent in ["reporter", "logger"]:
                score = 0.3  # Always useful but not primary
            agent_scores.append((score, agent))

        # Sort by relevance, remove low-scoring
        agent_scores.sort(key=lambda x: -x[0])
        route = [a for s, a in agent_scores if s >= 0.5]

        if not route:
            route = agents[:2]  # Default: first 2 agents

        return route

    # ── P69: Agent Knowledge Distillation ───────────────────

    def distill(self, source: str, target: str, knowledge: str,
                confidence: float = 0.8):
        """Distill knowledge from one agent to another."""
        entry = f"[from {source}] {knowledge[:200]}"
        self.knowledge[target].append(entry)
        self._save()

    def get_distilled(self, agent: str) -> list[str]:
        """Get distilled knowledge for an agent."""
        return self.knowledge.get(agent, [])


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="agent_intel", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    intel = AgentIntel()

    # Loop distill
    s = sub.add_parser("loop-distill", help="Record loop for distillation")
    s.add_argument("--success", required=True)
    s.add_argument("--tokens", type=int, default=1000)
    s.add_argument("--agent", default="")
    s.set_defaults(func=lambda a: _loop(intel, a))

    # Skill RAG
    s2 = sub.add_parser("skill-rag", help="Select skills for task")
    s2.add_argument("task", help="Task description")
    s2.add_argument("--budget", type=int, default=4000)
    s2.set_defaults(func=lambda a: _skill(intel, a))

    # Predict fix
    s3 = sub.add_parser("predict-fix", help="Predict fix cost")
    s3.add_argument("issue", help="Issue description")
    s3.add_argument("--budget", type=int, default=2000)
    s3.set_defaults(func=lambda a: print(json.dumps(intel.predict_fix(a.issue, a.budget), indent=2)))

    # Memory compress
    s4 = sub.add_parser("mem-compress", help="Compress agent memory")
    s4.add_argument("memory", help="Memory text")
    s4.add_argument("--agent", default="default")
    s4.set_defaults(func=lambda a: print(intel.compress_memory(a.agent, a.memory)))

    # Predict route
    s5 = sub.add_parser("predict-route", help="Predict agent route")
    s5.add_argument("task", help="Task description")
    s5.add_argument("--agents", nargs="+", default=[])
    s5.set_defaults(func=lambda a: print("→ " + " → ".join(intel.predict_route(a.task, a.agents))))

    # Distill
    s6 = sub.add_parser("distill", help="Distill knowledge")
    s6.add_argument("--from", dest="source", required=True)
    s6.add_argument("--to", dest="target", required=True)
    s6.add_argument("knowledge", help="Knowledge to transfer")
    s6.set_defaults(func=lambda a: _distill(intel, a))

    # Stats
    sub.add_parser("stats", help="Show all stats").set_defaults(
        func=lambda a: print(json.dumps({
            "loops": intel.loop_stats(),
            "skills": len(intel.skills),
            "fixes": len(intel.fixes),
            "knowledge_transfers": sum(len(v) for v in intel.knowledge.values()),
        }, indent=2)))

    args = p.parse_args(argv)
    return 0


def _loop(intel: AgentIntel, args):
    intel.record_loop(args.success, args.tokens, True, args.agent)
    print(f"✅ Loop recorded ({args.tokens} tok)")


def _skill(intel: AgentIntel, args):
    selected = intel.select_skills(args.task, args.budget)
    total = sum(s["tokens"] for s in selected)
    print(f"Selected {len(selected)} skills ({total} tokens):")
    for s in selected:
        print(f"  {s['name']:<20} rel={s['relevance']:.2f}  {s['tokens']}tok")


def _distill(intel: AgentIntel, args):
    intel.distill(args.source, args.target, args.knowledge)
    print(f"✅ Distilled from '{args.source}' → '{args.target}'")


if __name__ == "__main__":
    main()
