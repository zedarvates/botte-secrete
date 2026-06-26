"""registry — découvre automatiquement les skills Botte disponibles comme outils MCP.

Scanne skills/*/SKILL.md pour extraire le nom, la description,
et génère un schéma d'entrée MCP.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SkillTool:
    """MCP tool definition discovered from a Botte skill."""
    name: str                    # snake_case tool name
    label: str                   # human-readable name
    description: str             # from SKILL.md description field
    module_path: str             # python -m path
    extra_args: list[dict] = field(default_factory=list)
    enabled: bool = True


# ── Built-in skill tool definitions ──
# When SKILL.md is not available or auto-discovery fails, use these.
_BUILTIN_SKILLS: list[SkillTool] = [
    SkillTool("security_scanner", "Security Scanner",
              "Scan code for malicious patterns: eval, exec, shell injection, env leaks, etc.",
              "skills.security_scanner.cli",
              extra_args=[{"name": "--format", "type": "string", "default": "compact",
                          "description": "Output format (compact/json/markdown)"}]),
    SkillTool("fast_context", "FastContext Agent",
              "Explore a codebase: find imports, functions, tests, patterns, or security issues.",
              "skills.fast_context.cli",
              extra_args=[{"name": "--format", "type": "string", "default": "compact"}]),
    SkillTool("meta_harness", "Meta-Harness",
              "Run a multi-agent pipeline: audit, fix, test, security scan.",
              "skills.meta_harness.cli",
              extra_args=[{"name": "--approval", "type": "boolean", "default": False}]),
    SkillTool("botte_nn", "Tiny Neural Network",
              "Classify task effort, route local/cloud, detect anomalies. 0 token inference.",
              "skills.botte_nn.cli"),
    SkillTool("solvers", "Deterministic Solvers",
              "OR-Tools in stdlib: assign work, pack items, schedule steps.",
              "skills.solvers.cli"),
    SkillTool("context_budget", "Context Budget",
              "Optimal context to load under a token budget (knapsack).",
              "skills.context_budget.cli"),
    SkillTool("nlp_deterministic", "NLP Deterministic",
              "Classify and extract without an LLM (0 cloud tokens).",
              "skills.nlp_deterministic.cli"),
    SkillTool("checkup", "Checkup",
              "Security and quality audit with CI integration.",
              "skills.checkup.cli",
              extra_args=[{"name": "--format", "type": "string", "default": "json"}]),
    SkillTool("infra_advisor", "Infra Advisor",
              "Hardware/software infra tips for cost reduction.",
              "skills.infra_advisor.cli"),
    SkillTool("llm_backends", "LLM Backends Audit",
              "Discover and audit local LLM servers (LM Studio, Ollama, LocalAI).",
              "skills.llm_backends.cli"),
    SkillTool("metrics", "Token Metrics",
              "Track and report token savings per component.",
              "skills.metrics.cli"),
    SkillTool("cogniarc_eval", "CogniARC Evaluator",
              "ARC-AGI-3 game solver — run games, benchmark, manage symbol memory.",
              "cogniarc.bridge",
              extra_args=[
                  {"name": "cmd", "type": "string", "enum": ["run", "benchmark", "list", "memory"],
                   "description": "Command"},
                  {"name": "--game", "type": "string"},
                  {"name": "--agent", "type": "string", "default": "v4"},
              ]),
]


def discover_skills() -> list[SkillTool]:
    """Auto-discover Botte skills by scanning skills/*/SKILL.md.

    Falls back to _BUILTIN_SKILLS if SKILL.md parsing fails.
    """
    skills_dir = REPO_ROOT / "skills"
    discovered: list[SkillTool] = []
    seen: set[str] = set()

    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                tool = _parse_skill_md(skill_md)
                if tool and tool.name not in seen:
                    discovered.append(tool)
                    seen.add(tool.name)

    # Fallback: add builtins not already discovered
    for builtin in _BUILTIN_SKILLS:
        if builtin.name not in seen:
            discovered.append(builtin)
            seen.add(builtin.name)

    return discovered


def _parse_skill_md(path: Path) -> Optional[SkillTool]:
    """Parse a SKILL.md file to extract tool metadata."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Extract name
    name_match = re.search(r'^name:\s*(\S+)', text, re.MULTILINE)
    if not name_match:
        return None

    name = name_match.group(1).replace("-", "_")
    label = name.replace("_", " ").title()

    # Extract description
    desc_match = re.search(r'^description:\s*(.+)', text, re.MULTILINE)
    description = desc_match.group(1).strip() if desc_match else f"Botte skill: {name}"

    # Module path
    module_path = f"skills.{name}.cli"

    return SkillTool(
        name=name,
        label=label,
        description=description,
        module_path=module_path,
    )


def load_config() -> dict:
    """Load MCP gateway config from .botte-cache/mcp_gateway.json."""
    config_path = REPO_ROOT / ".botte-cache" / "mcp_gateway.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"enabled_skills": [], "excluded_skills": []}
