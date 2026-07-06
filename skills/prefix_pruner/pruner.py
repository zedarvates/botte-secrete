"""Prefix Pruner — prefix tree + context diffing + section pruning.

Analyse les préfixes de contexte, détecte les sections inutilisées,
et élague automatiquement ce qui n'est pas nécessaire.

Stratégies :
1. Section-level pruning — marque/démarque les blocs de contexte
2. Prefix tree — arbre global des préfixes pour tous les agents
3. Diffing contextuel — ne charger que les branches utiles
4. Usage tracking — track quelles sections sont réellement lues

Usage:
    python -m skills.prefix_pruner.cli prune --input context.txt --output pruned.txt
    python -m skills.prefix_pruner.cli tree --show
    python -m skills.prefix_pruner.cli stats
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data ───────────────────────────────────────────────────────

PREFIX_STORE = Path.home() / ".botte" / "prefix-tree.json"


@dataclass
class SectionNode:
    """A node in the prefix tree."""
    section_id: str
    section_type: str  # "system", "context", "skills", "memory", "tools", "unknown"
    content_hash: str
    token_count: int
    use_count: int = 0
    skip_count: int = 0
    children: list = field(default_factory=list)
    last_used: float = field(default_factory=time.time)
    created: float = field(default_factory=time.time)

    @property
    def usefulness(self) -> float:
        """Ratio of use to skip — how often this section actually matters."""
        total = self.use_count + self.skip_count
        if total == 0:
            return 0.5  # Neutral for new sections
        return self.use_count / total


class PrefixTree:
    """Global prefix tree tracking which context sections are actually useful."""

    def __init__(self):
        self.sections: dict[str, SectionNode] = {}
        self._load()

    def _load(self):
        if PREFIX_STORE.exists():
            try:
                data = json.loads(PREFIX_STORE.read_text())
                for sid, d in data.get("sections", {}).items():
                    self.sections[sid] = SectionNode(**d)
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        PREFIX_STORE.parent.mkdir(parents=True, exist_ok=True)
        PREFIX_STORE.write_text(json.dumps({
            "sections": {sid: {
                "section_id": s.section_id,
                "section_type": s.section_type,
                "content_hash": s.content_hash,
                "token_count": s.token_count,
                "use_count": s.use_count,
                "skip_count": s.skip_count,
                "last_used": s.last_used,
                "created": s.created,
            } for sid, s in self.sections.items()},
        }, indent=2))

    def register_section(self, section_id: str, section_type: str,
                         content: str, token_count: int):
        """Register or update a context section."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        if section_id in self.sections:
            node = self.sections[section_id]
            if node.content_hash != content_hash:
                # Content changed — reset counters
                node.content_hash = content_hash
                node.token_count = token_count
                node.use_count = 0
                node.skip_count = 0
            node.last_used = time.time()
        else:
            self.sections[section_id] = SectionNode(
                section_id=section_id,
                section_type=section_type,
                content_hash=content_hash,
                token_count=token_count,
            )
        self._save()

    def record_use(self, section_id: str):
        """Record that a section was actually used by the agent."""
        if section_id in self.sections:
            self.sections[section_id].use_count += 1
            self.sections[section_id].last_used = time.time()
            self._save()

    def record_skip(self, section_id: str):
        """Record that a section was skipped (not needed)."""
        if section_id in self.sections:
            self.sections[section_id].skip_count += 1
            self._save()

    def prune(self, min_usefulness: float = 0.3,
              max_age_days: int = 30) -> list[str]:
        """Get list of section IDs that can be pruned.

        A section is prunable if:
        - Its usefulness is below min_usefulness (used less than skipped)
        - OR it hasn't been used in max_age_days
        """
        now = time.time()
        prunable = []
        for sid, node in self.sections.items():
            age_days = (now - node.last_used) / 86400
            if node.usefulness < min_usefulness and node.use_count > 0:
                prunable.append(sid)
            elif age_days > max_age_days and node.use_count == 0:
                prunable.append(sid)
        return prunable

    def stats(self) -> dict:
        """Return tree statistics."""
        total = len(self.sections)
        if total == 0:
            return {"total_sections": 0}

        used = sum(1 for s in self.sections.values() if s.use_count > 0)
        skipped = sum(1 for s in self.sections.values() if s.skip_count > 0)
        total_tokens = sum(s.token_count for s in self.sections.values())
        wasted_tokens = sum(
            s.token_count for s in self.sections.values()
            if s.usefulness < 0.3 and s.use_count > 0
        )

        return {
            "total_sections": total,
            "used_sections": used,
            "skipped_sections": skipped,
            "total_tokens": total_tokens,
            "wasted_tokens": wasted_tokens,
            "wasted_pct": round(wasted_tokens / max(total_tokens, 1) * 100, 1),
            "by_type": dict(Counter(s.section_type for s in self.sections.values())),
        }


# ── Content pruner ─────────────────────────────────────────────

SECTION_PATTERNS = [
    (r'(#{1,3}\s*Context|#{1,3}\s*Background).*?(?=#{1,3}\s|\Z)', "context"),
    (r'(#{1,3}\s*Skills|#{1,3}\s*Capabilities).*?(?=#{1,3}\s|\Z)', "skills"),
    (r'(#{1,3}\s*Memory|#{1,3}\s*Remember).*?(?=#{1,3}\s|\Z)', "memory"),
    (r'(#{1,3}\s*Tools|#{1,3}\s*Available).*?(?=#{1,3}\s|\Z)', "tools"),
    (r'<system>.*?</system>', "system"),
    (r'<context>.*?</context>', "context"),
]


def split_sections(content: str) -> list[dict]:
    """Split content into named sections."""
    sections = []
    remaining = content

    for pattern, section_type in SECTION_PATTERNS:
        matches = list(re.finditer(pattern, remaining, re.DOTALL))
        for m in matches:
            sections.append({
                "type": section_type,
                "content": m.group(0),
                "start": m.start(),
                "end": m.end(),
            })

    if not sections:
        sections.append({
            "type": "unknown",
            "content": content,
            "start": 0,
            "end": len(content),
        })

    return sections


def prune_content(content: str, tree: Optional[PrefixTree] = None,
                  strategy: str = "auto") -> str:
    """Prune unnecessary sections from content.

    Strategies:
    - auto: use prefix tree to decide what to keep
    - aggressive: remove all low-usefulness sections
    - conservative: only remove sections never used
    """
    if tree is None:
        tree = PrefixTree()

    sections = split_sections(content)
    if len(sections) <= 1:
        return content  # Nothing to prune

    pruned = []
    total_pruned_tokens = 0

    for section in sections:
        section_id = hashlib.sha256(section["content"].encode()).hexdigest()[:12]
        token_count = len(section["content"]) // 4

        tree.register_section(section_id, section["type"],
                              section["content"], token_count)

        if strategy == "aggressive":
            keep = tree.sections[section_id].usefulness >= 0.3
        elif strategy == "conservative":
            keep = tree.sections[section_id].use_count > 0 or tree.sections[section_id].skip_count == 0
        else:  # auto
            # Keep if used more than skipped, or if new
            keep = tree.sections[section_id].usefulness >= 0.3 or tree.sections[section_id].use_count == 0

        if keep:
            pruned.append(section["content"])
            tree.record_use(section_id)
        else:
            total_pruned_tokens += token_count
            tree.record_skip(section_id)

    result = "\n\n".join(pruned)

    if total_pruned_tokens > 0:
        print(f"  ✂️ Pruned {total_pruned_tokens} tokens (removed {len(sections) - len(pruned)} sections)")

    return result
