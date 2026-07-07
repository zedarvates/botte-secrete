"""botte learn — analyse les sessions d'agents et écrit des corrections.

Inspiré par 'headroom learn' qui mine les sessions échouées et écrit
des corrections dans CLAUDE.md / AGENTS.md.

Fonctionnement :
1. Analyse les logs proxy (erreurs, temps de réponse, patterns)
2. Analyse les logs Hermes (sessions échouées, commandes en échec)
3. Détecte les patterns répétés (mêmes erreurs, boucles)
4. Génère des règles de correction
5. Les écrit dans AGENTS.md, .botte/learn/rules.md

Usage:
    python -m skills.botte_learn.cli scan           # Analyser les logs
    python -m skills.botte_learn.cli apply          # Appliquer les corrections
    python -m skills.botte_learn.cli status         # Voir les règles actives
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Paths ──────────────────────────────────────────────────────

BOTTE_LEARN_DIR = Path.home() / ".botte" / "learn"
BOTTE_RULES_FILE = BOTTE_LEARN_DIR / "rules.json"
BOTTE_AGENTS_MD = Path("AGENTS.md")
BOTTE_CLAUDE_MD = Path("CLAUDE.md")


# ── Data structures ────────────────────────────────────────────

@dataclass
class ObservedPattern:
    """A pattern observed across sessions."""
    pattern_type: str  # "error", "slow_request", "cache_miss", "command_failure"
    pattern: str       # The pattern text/regex
    count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    example: str = ""
    suggested_rule: str = ""


@dataclass
class LearnedRule:
    """A correction rule generated from observed patterns."""
    rule_id: str
    source: str  # "auto" or "manual"
    trigger: str  # What triggers this rule
    action: str   # What to do
    target_file: str  # Where to write (AGENTS.md, CLAUDE.md, etc.)
    count: int = 1
    created: float = field(default_factory=time.time)
    applied: bool = False


# ── Analyzer ───────────────────────────────────────────────────

class SessionAnalyzer:
    """Analyze proxy logs and session data for failure patterns."""

    def __init__(self):
        self.patterns: list[ObservedPattern] = []
        self.rules: list[LearnedRule] = []
        self._load()

    def _load(self):
        """Load previously observed patterns and rules."""
        BOTTE_LEARN_DIR.mkdir(parents=True, exist_ok=True)
        if BOTTE_RULES_FILE.exists():
            try:
                data = json.loads(BOTTE_RULES_FILE.read_text())
                self.patterns = [ObservedPattern(**p) for p in data.get("patterns", [])]
                self.rules = [LearnedRule(**r) for r in data.get("rules", [])]
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        """Save patterns and rules."""
        BOTTE_LEARN_DIR.mkdir(parents=True, exist_ok=True)
        BOTTE_RULES_FILE.write_text(json.dumps({
            "patterns": [
                {"pattern_type": p.pattern_type, "pattern": p.pattern,
                 "count": p.count, "first_seen": p.first_seen,
                 "last_seen": p.last_seen, "example": p.example,
                 "suggested_rule": p.suggested_rule}
                for p in self.patterns
            ],
            "rules": [
                {"rule_id": r.rule_id, "source": r.source,
                 "trigger": r.trigger, "action": r.action,
                 "target_file": r.target_file, "count": r.count,
                 "created": r.created, "applied": r.applied}
                for r in self.rules
            ],
        }, indent=2))

    def scan_proxy_stats(self, stats_file: Optional[Path] = None):
        """Analyze proxy statistics for error patterns."""
        # Try proxy stats endpoint
        stats_data = None
        if stats_file and stats_file.exists():
            stats_data = json.loads(stats_file.read_text())

        if not stats_data:
            # Try to fetch from running proxy
            try:
                import urllib.request
                with urllib.request.urlopen("http://localhost:8787/stats", timeout=2) as resp:
                    stats_data = json.loads(resp.read())
            except Exception:
                pass

        if not stats_data:
            print("  ⚠️  No proxy stats available. Start the proxy first.")
            return

        # Analyze errors
        errors = stats_data.get("errors", 0)
        total = stats_data.get("total_requests", 0)
        if total > 0 and errors / total > 0.1:
            pattern = ObservedPattern(
                pattern_type="error",
                pattern=f"high_error_rate:{errors}/{total}",
                count=int(errors),
                example=f"{errors} errors in {total} requests ({round(errors/total*100,1)}%)",
                suggested_rule="Check proxy target URL and API key configuration",
            )
            self.patterns.append(pattern)
            print(f"  📊 High error rate: {errors}/{total} ({round(errors/total*100,1)}%)")

        # Analyze cache hit rate
        cache = stats_data.get("cache", {})
        cache_hits = cache.get("cache_hits", 0)
        cache_total = cache.get("total_requests", 0)
        if cache_total > 0:
            hit_rate = cache_hits / cache_total * 100
            if hit_rate < 30:
                pattern = ObservedPattern(
                    pattern_type="cache_miss",
                    pattern="low_cache_hit_rate",
                    count=cache_total - cache_hits,
                    example=f"Cache hit rate: {round(hit_rate,1)}% ({cache_hits}/{cache_total})",
                    suggested_rule="Ensure system prompt is stable across requests for better KV cache hits",
                )
                self.patterns.append(pattern)
                print(f"  📊 Low cache hit rate: {round(hit_rate,1)}%")

        # Analyze slow requests
        avg_time = stats_data.get("avg_time_ms", 0)
        if avg_time > 5000:
            pattern = ObservedPattern(
                pattern_type="slow_request",
                pattern="high_avg_latency",
                count=total,
                example=f"Avg response time: {avg_time}ms",
                suggested_rule="Consider using a faster model or local endpoint",
            )
            self.patterns.append(pattern)
            print(f"  📊 High latency: {avg_time}ms avg")

        print(f"  ✅ Scanned proxy stats: {total} requests, {errors} errors")

    def scan_hermes_sessions(self):
        """Analyze Hermes session logs for failure patterns."""
        hermes_cache = Path.home() / ".hermes"
        session_db = hermes_cache / "sessions.db"
        if not session_db.exists():
            print("  ⚠️  No Hermes session data found")
            return

        # Use session_search-like logic to find patterns
        # For now, look at proxy log files
        proxy_logs = list(BOTTE_LEARN_DIR.parent.glob("proxy*.log"))
        proxy_logs.extend(list(Path("/tmp").glob("botte_proxy*.log")))

        if proxy_logs:
            error_patterns = Counter()
            for log_file in proxy_logs:
                content = log_file.read_text() if log_file.exists() else ""
                for line in content.split("\n"):
                    if "error" in line.lower() or "fail" in line.lower():
                        # Extract model name and error
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if "error" in p.lower() or "fail" in p.lower():
                                context = " ".join(parts[max(0, i - 2):i + 2])
                                error_patterns[context] += 1

            for context, count in error_patterns.most_common(5):
                if count >= 2:  # Only flag repeated errors
                    pattern = ObservedPattern(
                        pattern_type="command_failure",
                        pattern=context[:100],
                        count=count,
                        example=context,
                        suggested_rule=f"Repeated error ({count}x): {context[:80]}",
                    )
                    self.patterns.append(pattern)
                    print(f"  📊 Repeated error ({count}x): {context[:80]}...")

        print(f"  ✅ Scanned {len(proxy_logs)} log files")

    def generate_rules(self) -> list[LearnedRule]:
        """Generate correction rules from observed patterns."""
        new_rules = []

        for pattern in self.patterns:
            if not pattern.suggested_rule:
                continue

            # Check if a similar rule already exists
            already_exists = any(
                r.trigger in pattern.pattern or pattern.pattern in r.trigger
                for r in self.rules
            )
            if already_exists:
                # Update count on existing rule
                for r in self.rules:
                    if pattern.pattern in r.trigger:
                        r.count += 1
                continue

            rule = LearnedRule(
                rule_id=f"rule_{int(time.time())}_{len(new_rules)}",
                source="auto",
                trigger=pattern.pattern,
                action=pattern.suggested_rule,
                target_file="AGENTS.md",
            )
            new_rules.append(rule)

        self.rules.extend(new_rules)
        self._save()
        return new_rules

    def apply_rules(self, target: Optional[str] = None) -> int:
        """Write correction rules to AGENTS.md, CLAUDE.md, etc.

        Returns number of rules applied.
        """
        applied = 0
        rules_by_target = defaultdict(list)
        for rule in self.rules:
            if not rule.applied:
                rules_by_target[rule.target_file].append(rule)

        for target_file, rules in rules_by_target.items():
            if target and target_file != target:
                continue

            filepath = Path(target_file)
            if not rules:
                continue

            # Build rules section
            rules_section = "\n## 🔧 Auto-generated rules (botte learn)\n\n"
            for rule in rules:
                rules_section += f"- **{rule.trigger[:60]}**: {rule.action}\n"
            rules_section += "\n"

            # Append to file
            if filepath.exists():
                content = filepath.read_text()
                # Remove old botte learn section if exists
                content = re.sub(
                    r'\n## 🔧 Auto-generated rules \(botte learn\).*?(?=\n## |\Z)',
                    '',
                    content,
                    flags=re.DOTALL,
                )
                content += rules_section
            else:
                content = f"# Agent Instructions\n{rules_section}"

            filepath.write_text(content)
            for rule in rules:
                rule.applied = True
                applied += 1
            print(f"  ✍️  Wrote {len(rules)} rules to {target_file}")

        self._save()
        return applied

    def status(self) -> dict:
        """Return current status."""
        return {
            "patterns_observed": len(self.patterns),
            "rules_generated": len(self.rules),
            "rules_applied": sum(1 for r in self.rules if r.applied),
            "by_type": dict(Counter(p.pattern_type for p in self.patterns)),
            "recent_rules": [
                {"id": r.rule_id, "trigger": r.trigger[:60],
                 "action": r.action[:80], "applied": r.applied}
                for r in self.rules[-10:]
            ],
        }
