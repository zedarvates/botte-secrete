"""Skill optimizer — match skills to project profile and generate .skills-profile."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional

from skills.skill_project_optimizer.scanner import SkillInfo, SkillScanResult
from skills.skill_project_optimizer.profiler import ProjectProfile


# Skill-to-project matching rules
# Each rule: (condition_func, skill_tags_or_names, priority)
SKILL_MATCHING_RULES = [
    # Core skills — always relevant
    (lambda p: True, {"writing-plans", "code-rules"}, "always"),
    (lambda p: True, {"simplify-code"}, "always"),

    # GitHub/Git
    (lambda p: p.has_github_remote, {"github", "github-workflow"}, "high"),
    (lambda p: p.has_git, {"github"}, "medium"),

    # CI/CD
    (lambda p: p.has_ci, {"ci", "devops", "github"}, "high"),

    # Docker
    (lambda p: p.has_docker, {"docker", "devops"}, "high"),

    # Web frontend
    (lambda p: p.type == "web-frontend", {"frontend", "web-design", "ui", "css", "html"}, "high"),
    (lambda p: "react" in p.frameworks, {"frontend", "web-design"}, "medium"),

    # Web backend
    (lambda p: p.type == "web-backend", {"backend", "api", "server"}, "high"),
    (lambda p: "fastapi" in p.frameworks, {"backend", "api"}, "medium"),

    # ML/Data
    (lambda p: p.type == "ml", {"mlops", "training", "evaluation", "ml"}, "high"),
    (lambda p: "jupyter" in str(p.languages.keys()), {"mlops"}, "medium"),

    # CLI
    (lambda p: p.type == "cli", {"cli", "terminal"}, "high"),

    # Infrastructure
    (lambda p: p.type == "infra", {"devops", "infrastructure", "cluster"}, "high"),

    # Rust
    (lambda p: "rust" in str(p.languages.keys()), {"rust", "cargo"}, "medium"),

    # Python
    (lambda p: ".py" in p.languages, {"python", "devops"}, "low"),

    # TypeScript
    (lambda p: ".ts" in p.languages, {"typescript", "frontend"}, "low"),

    # Research
    (lambda p: "research" in p.directories, {"research", "pipeline"}, "medium"),

    # Trading/Finance
    (lambda p: "trading" in str(p.directories).lower() or "finance" in str(p.directories).lower(),
     {"turboquant", "trading"}, "high"),

    # Hardware/AI
    (lambda p: "vision" in str(p.directories).lower() or "camera" in str(p.directories).lower(),
     {"hailo", "vision", "comfyui"}, "high"),
]


@dataclass
class OptimizationResult:
    """Result of skill optimization for a project."""
    profile: ProjectProfile = field(default_factory=ProjectProfile)
    matched_skills: list[tuple[SkillInfo, str]] = field(default_factory=list)  # (skill, priority)
    excluded_skills: list[tuple[SkillInfo, str]] = field(default_factory=list)  # (skill, reason)
    total_available_tokens: int = 0
    total_loaded_tokens: int = 0
    savings_tokens: int = 0
    savings_percent: float = 0.0

    def summary(self) -> str:
        lines = [
            f"📊 Skill Optimization Summary",
            f"{'='*50}",
            f"Project: {self.profile.name} ({self.profile.type})",
            f"Languages: {', '.join(f'{k}:{v}' for k,v in list(self.profile.languages.items())[:5])}",
            f"Frameworks: {', '.join(self.profile.frameworks[:5])}",
            f"",
            f"Available tokens: {self.total_available_tokens:,}",
            f"Loaded tokens:    {self.total_loaded_tokens:,}",
            f"Savings:          {self.savings_tokens:,} ({self.savings_percent:.0f}%)",
            f"",
            f"Matched skills ({len(self.matched_skills)}):",
        ]

        # Group by priority
        for priority in ["always", "high", "medium", "low"]:
            group = [(s, p) for s, p in self.matched_skills if p == priority]
            if group:
                lines.append(f"\n  [{priority.upper()}]")
                for skill, _ in group[:10]:
                    lines.append(f"    • {skill.name} ({skill.estimated_tokens:,} tokens)")
                if len(group) > 10:
                    lines.append(f"    ... +{len(group)-10} more")

        if self.excluded_skills:
            lines.append(f"\nExcluded ({len(self.excluded_skills)}):")
            for skill, reason in self.excluded_skills[:20]:
                lines.append(f"    ✗ {skill.name} ({reason})")

        return "\n".join(lines)


def optimize_skills(
    scan_result: SkillScanResult,
    profile: ProjectProfile,
) -> OptimizationResult:
    """Match skills to project profile and determine which to load."""
    result = OptimizationResult()
    result.profile = profile
    result.total_available_tokens = scan_result.active_tokens  # Only count active

    matched_names: set[str] = set()

    # Apply matching rules
    for condition, tags_or_names, priority in SKILL_MATCHING_RULES:
        if not condition(profile):
            continue
        for skill in scan_result.skills:
            if skill.is_archived or skill.name in matched_names:
                continue
            # Match by tags
            skill_tags_lower = {t.lower() for t in skill.tags}
            rule_tags_lower = {t.lower() for t in tags_or_names}
            # Match by name
            name_match = skill.name.lower() in {n.lower() for n in tags_or_names}
            # Match by description
            desc_lower = skill.description.lower()
            desc_match = any(t.lower() in desc_lower for t in tags_or_names)

            if name_match or skill_tags_lower & rule_tags_lower or desc_match:
                result.matched_skills.append((skill, priority))
                matched_names.add(skill.name)

    # Sort: always first, then by priority, then by size (smaller first)
    priority_order = {"always": 0, "high": 1, "medium": 2, "low": 3}
    result.matched_skills.sort(key=lambda x: (priority_order.get(x[1], 9), x[0].estimated_tokens))

    # Excluded = active but not matched
    for skill in scan_result.skills:
        if not skill.is_archived and skill.name not in matched_names:
            reason = "archived" if skill.is_archived else "not matched to project"
            result.excluded_skills.append((skill, reason))

    # Calculate savings
    loaded_tokens = sum(s.estimated_tokens for s, _ in result.matched_skills)
    result.total_loaded_tokens = loaded_tokens
    result.savings_tokens = result.total_available_tokens - loaded_tokens
    result.savings_percent = (
        (result.savings_tokens / result.total_available_tokens * 100)
        if result.total_available_tokens > 0 else 0
    )

    return result


def generate_skills_profile(
    result: OptimizationResult,
    output_path: Path,
) -> Path:
    """Generate .skills-profile.yaml for a project."""
    always = [s.name for s, p in result.matched_skills if p == "always"]
    conditional = [s.name for s, p in result.matched_skills if p != "always"]
    disabled = [s.name for s, _ in result.excluded_skills if not s.is_archived]

    lines = [
        "# .skills-profile — Generated by skill-project-optimizer",
        "# Place this file in your project root",
        "# Only listed skills will be loaded for this project",
        "",
        "project:",
        f"  name: \"{result.profile.name}\"",
        f"  type: \"{result.profile.type}\"",
        f"  languages: [{', '.join(repr(k) for k in list(result.profile.languages.keys())[:5])}],",
        f"  frameworks: [{', '.join(repr(f) for f in result.profile.frameworks[:5])}],",
        "",
        "skills:",
        "  # Core — always loaded",
        "  always:",
    ]
    for name in always:
        lines.append(f"    - {name}")

    lines.extend(["", "  # Conditional — loaded based on project match", "  conditional:"])
    for name in conditional[:20]:
        lines.append(f"    - {name}")

    if disabled:
        lines.extend(["", "  # Disabled — excluded from this project", "  disabled:"])
        for name in disabled[:20]:
            lines.append(f"    - {name}")

    lines.extend([
        "",
        "# Token savings",
        "stats:",
        f"  total_available: {result.total_available_tokens}",
        f"  total_loaded: {result.total_loaded_tokens}",
        f"  savings_percent: {result.savings_percent:.0f}%",
    ])

    content = "\n".join(lines)
    output_path.write_text(content)
    return output_path