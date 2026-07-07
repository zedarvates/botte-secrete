#!/usr/bin/env python3
"""Ticket Generator — Convert audit findings into actionable tickets for coding agents.

Output formats:
    --json      : JSON array (for API/GitHub issues)
    --markdown  : Markdown checklist (for copy-paste into issues/PRs)
    --csv       : CSV spreadsheet import

Usage:
    python3 skills/generate_tickets.py audit-report.json --json > tickets.json
    python3 skills/generate_tickets.py audit-report.json --markdown
    python3 skills/generate_tickets.py audit-report.json --csv > tickets.csv
"""

import sys
import json
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.console_utf8 import force_utf8  # noqa: E402 — avant tout print d'émoji

force_utf8()


class Ticket:
    """A single improvement ticket derived from an audit finding."""

    def __init__(self, finding: dict, index: int, project: str = ""):
        self.id = f"BS-{index + 1:04d}"
        self.file = finding.get("f", finding.get("file", "unknown"))
        self.type = finding.get("t", finding.get("type", "unknown"))
        self.severity = finding.get("s", finding.get("severity", "err"))
        self.title = finding.get("d", finding.get("description", finding.get("message", "No description")))
        # Truncate verbose repr strings
        if len(self.title) > 120 or "severity=<" in self.title:
            self.title = finding.get("message", finding.get("fix_hint", "No description"))[:120]
        self.project = project

        # Priority mapping
        sev_to_priority = {"crit": "P0", "err": "P1", "warn": "P2", "info": "P2"}
        self.priority = finding.get("p", sev_to_priority.get(self.severity, "P2"))

        # Agent assignment
        type_to_agent = {
            "dead": "⚔️ d'Artagnan",
            "dup": "⚔️ d'Artagnan",
            "cmp": "📿 Aramis",
            "sec": "🥊 Porthos",
            "bnd": "📿 Aramis",
            "flg": "⚔️ d'Artagnan",
        }
        self.agent = type_to_agent.get(self.type, "🥊 Porthos")

        # Labels
        self.labels = ["botte-secrete", self.priority.lower(), self.type]

        # Complexity estimate
        complexity_map = {"dead": 1, "dup": 2, "cmp": 5, "sec": 8, "bnd": 3, "flg": 2}
        self.complexity = complexity_map.get(self.type, 3)

    def to_github_issue(self) -> dict:
        """Format as GitHub issue payload."""
        return {
            "title": f"[{self.priority}] {self.id}: {self.title}",
            "body": "\n".join([
                f"**ID:** {self.id}",
                f"**Agent:** {self.agent}",
                f"**Fichier:** `{self.file}`",
                f"**Type:** {self.type}",
                f"**Priorité:** {self.priority}",
                f"**Sévérité:** {self.severity}",
                f"**Complexité estimée:** {self.complexity}/10",
                "",
                "## 📋 Instructions pour l'agent codeur",
                "",
                self._agent_instructions(),
                "",
                "---",
                f"*Généré par Botte Secrète le {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            ]),
            "labels": self.labels,
        }

    def _agent_instructions(self) -> str:
        """Generate agent-specific instructions."""
        instructions = {
            "dead": "1. Vérifier que le code est vraiment mort (grep -r)\n2. Commenter avec # DEAD CODE: [raison]\n3. Vérifier que les imports sont toujours valides",
            "dup": "1. Identifier la duplication exacte\n2. Extraire en fonction/classe partagée\n3. Remplacer les 3 occurrences\n4. Exécuter les tests",
            "cmp": "1. Identifier la source de complexité\n2. Splitter en sous-fonctions (max 15 lignes)\n3. Simplifier les conditions\n4. Exécuter les tests",
            "sec": "1. LOCALISER la fuite immédiatement\n2. Supprimer le secret du code\n3. Utiliser une variable d'environnement\n4. Vérifier les logs (pas de trace)",
            "bnd": "1. Vérifier la règle d'architecture\n2. Déplacer le code dans la bonne couche\n3. Mettre à jour les imports\n4. Exécuter les tests",
            "flg": "1. Vérifier si le flag est vraiment stale\n2. Si oui, supprimer le flag + code dead\n3. Si non, mettre à jour la date\n4. Exécuter les tests",
        }
        return instructions.get(self.type, "1. Analyser le finding\n2. Appliquer le fix\n3. Vérifier\n4. Tester")

    def to_markdown(self) -> str:
        """Format as markdown checklist item."""
        return f"- [ ] **{self.id}** ({self.priority}) — {self.title} — `{self.file}` → {self.agent}"

    def to_csv_row(self) -> list:
        """Format as CSV row."""
        return [self.id, self.priority, self.severity, self.type, self.title, self.file,
                self.agent, str(self.complexity), self.project]


def load_findings(path: str) -> list[dict]:
    """Load findings from an audit report JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # Support both old and compact format
    if "fn" in data:
        return data["fn"]
    if "findings" in data:
        return data["findings"]
    if isinstance(data, list):
        return data
    return []


def main():
    # Windows cp1252 consoles crash on the emoji in the output below.
    for _s in (sys.stdout, sys.stderr):
        _rc = getattr(_s, "reconfigure", None)
        if _rc:
            try:
                _rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    report_path = sys.argv[1]
    fmt = "markdown"  # default
    for arg in sys.argv[2:]:
        if arg in ("--json", "--markdown", "--csv"):
            fmt = arg.lstrip("--")

    project = Path(report_path).parent.name
    findings = load_findings(report_path)

    if not findings:
        print("Aucun finding trouvé dans le rapport.")
        sys.exit(1)

    tickets = [Ticket(f, i, project) for i, f in enumerate(findings)]

    if fmt == "json":
        print(json.dumps([t.to_github_issue() for t in tickets], indent=2, ensure_ascii=False))
    elif fmt == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(["ID", "Priority", "Severity", "Type", "Title", "File", "Agent", "Complexity", "Project"])
        for t in tickets:
            writer.writerow(t.to_csv_row())
    else:
        # Markdown
        print(f"# 📋 Tickets Botte Secrète — {project}")
        print(f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"Total: {len(tickets)} tickets\n")

        by_priority = {}
        for t in tickets:
            by_priority.setdefault(t.priority, []).append(t)

        for p in ["P0", "P1", "P2"]:
            items = by_priority.get(p, [])
            if items:
                print(f"## {p} ({len(items)})")
                for t in items:
                    print(t.to_markdown())
                print()

        # Summary
        p0 = len(by_priority.get("P0", []))
        p1 = len(by_priority.get("P1", []))
        p2 = len(by_priority.get("P2", []))
        total_complexity = sum(t.complexity for t in tickets)
        print(f"---")
        print(f"**Résumé:** {len(tickets)} tickets · P0:{p0} P1:{p1} P2:{p2} · Complexité totale: {total_complexity}/10")


if __name__ == "__main__":
    main()
