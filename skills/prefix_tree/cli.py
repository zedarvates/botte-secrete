"""Prefix Tree — arbre des préfixes de prompts pour les boucles rétroactives.

Chaque agent a un préfixe stable. Les boucles rétroactives n'envoient
que les diffs, pas le prompt complet. Basé sur un trie compressé.

Usage:
    python -m skills.prefix_tree.cli register agent_name --prefix "system..."
    python -m skills.prefix_tree.cli diff agent_name "new content"
    python -m skills.prefix_tree.cli stats
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TREE_STORE = Path.home() / ".botte" / "prefix-tree-store.json"


class PrefixTrie:
    """Compressed prefix trie for agent prompts."""

    def __init__(self):
        self.agents: dict[str, str] = {}  # agent_name → full prefix
        self._load()

    def _load(self):
        if TREE_STORE.exists():
            try:
                data = json.loads(TREE_STORE.read_text())
                self.agents = data.get("agents", {})
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        TREE_STORE.parent.mkdir(parents=True, exist_ok=True)
        TREE_STORE.write_text(json.dumps({"agents": self.agents}, indent=2))

    def register(self, agent: str, prefix: str):
        """Register or update an agent's prompt prefix."""
        self.agents[agent] = prefix
        self._save()

    def get_prefix(self, agent: str) -> str:
        """Get the stored prefix for an agent."""
        return self.agents.get(agent, "")

    def diff(self, agent: str, new_content: str) -> str:
        """Compute delta between stored prefix and new content."""
        prefix = self.agents.get(agent, "")
        if not prefix:
            return new_content  # No prefix known — send full

        # Find common prefix length
        min_len = min(len(prefix), len(new_content))
        if prefix[:min_len] == new_content[:min_len]:
            # Same prefix — send only the new part
            diff = new_content[min_len:].strip()
            if diff:
                return f"[diff:+{len(diff)}c] {diff}"
            return "[no change]"

        # Different — send full but mark the difference
        return new_content

    def common_prefix(self, agents: list[str]) -> str:
        """Find the longest common prefix among multiple agents."""
        if not agents:
            return ""
        prefixes = [self.agents.get(a, "") for a in agents]
        if not prefixes or not prefixes[0]:
            return ""

        common = prefixes[0]
        for p in prefixes[1:]:
            i = 0
            while i < len(common) and i < len(p) and common[i] == p[i]:
                i += 1
            common = common[:i]
            if not common:
                break
        return common

    def stats(self) -> dict:
        """Return tree statistics."""
        total_chars = sum(len(p) for p in self.agents.values())
        return {
            "agents": len(self.agents),
            "total_prefix_chars": total_chars,
            "total_tokens_saved_est": total_chars // 4 * 3,  # Each reuse saves ~75%
            "agents_list": list(self.agents.keys()),
        }


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="prefix_tree", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    tree = PrefixTrie()

    s = sub.add_parser("register", help="Register agent prefix")
    s.add_argument("agent", help="Agent name")
    s.add_argument("--prefix", required=True, help="Prompt prefix")
    s.set_defaults(func=lambda a: _register(tree, a))

    s2 = sub.add_parser("diff", help="Compute prompt diff")
    s2.add_argument("agent", help="Agent name")
    s2.add_argument("content", help="New content to diff")
    s2.set_defaults(func=lambda a: print(tree.diff(a.agent, a.content)))

    s3 = sub.add_parser("common", help="Find common prefix")
    s3.add_argument("agents", nargs="+", help="Agent names")
    s3.set_defaults(func=lambda a: print(tree.common_prefix(a.agents)))

    sub.add_parser("stats", help="Show tree stats").set_defaults(
        func=lambda a: print(json.dumps(tree.stats(), indent=2)))

    args = p.parse_args(argv)
    return args.func(args) or 0


def _register(tree: PrefixTrie, args):
    tree.register(args.agent, args.prefix)
    print(f"✅ Registered prefix for '{args.agent}' ({len(args.prefix)} chars)")


if __name__ == "__main__":
    main()
