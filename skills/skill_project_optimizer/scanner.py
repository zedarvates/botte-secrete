"""Skill Project Optimizer — Scan, profile, and optimize skill loading per project."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re


@dataclass
class SkillInfo:
    """Metadata about a single skill."""
    name: str
    category: str
    path: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    size_chars: int = 0
    size_lines: int = 0
    estimated_tokens: int = 0
    is_archived: bool = False
    has_frontmatter: bool = False
    model: str = ""

    @property
    def token_cost(self) -> int:
        """Estimated token cost when loaded (chars / 4 is rough estimate)."""
        return self.estimated_tokens

    @property
    def qualified_name(self) -> str:
        return f"{self.category}/{self.name}"


@dataclass
class SkillScanResult:
    """Result of scanning all available skills."""
    skills: list[SkillInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_tokens: int = 0
    archived_tokens: int = 0
    active_tokens: int = 0


def scan_skills(skills_dir: str = "~/.hermes/skills") -> SkillScanResult:
    """Scan all skills and extract metadata."""
    result = SkillScanResult()
    skills_path = Path(skills_dir).expanduser()

    if not skills_path.exists():
        result.errors.append(f"Skills directory not found: {skills_path}")
        return result

    for category_dir in sorted(skills_path.iterdir()):
        if not category_dir.is_dir():
            continue

        is_archived = category_dir.name.startswith(".") or category_dir.name == ".archive"

        for skill_dir in sorted(category_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(errors="replace")
                chars = len(content)
                lines = len(content.splitlines())

                # Parse frontmatter
                fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
                tags = []
                desc = ""
                triggers = []
                allowed_tools = []
                model = ""

                if fm_match:
                    fm_text = fm_match.group(1)

                    # Tags
                    tags_m = re.search(r"tags:\s*\[(.*?)\]", fm_text, re.DOTALL)
                    if tags_m:
                        tags = [t.strip().strip("'\"") for t in tags_m.group(1).split(",") if t.strip()]

                    # Description
                    desc_m = re.search(r"description:\s*[\"']?(.*?)(?:[\"']?\n|$)", fm_text, re.DOTALL)
                    if desc_m:
                        desc = desc_m.group(1).strip()

                    # Allowed tools
                    tools_m = re.search(r"allowed_tools:\s*\[(.*?)\]", fm_text, re.DOTALL)
                    if tools_m:
                        allowed_tools = [t.strip().strip("'\"") for t in tools_m.group(1).split(",") if t.strip()]

                    # Model
                    model_m = re.search(r"model:\s*[\"']?(.*?)(?:[\"']?\n|$)", fm_text)
                    if model_m:
                        model = model_m.group(1).strip()

                    # Triggers (from "when to use" section)
                    trigger_section = re.search(r"(?:when to use|triggers?):\s*\n(.*?)(?:\n##|\Z)", content, re.IGNORECASE | re.DOTALL)
                    if trigger_section:
                        for line in trigger_section.group(1).splitlines():
                            line = line.strip().strip("-").strip()
                            if line:
                                triggers.append(line)
                else:
                    # No frontmatter — extract first paragraph as description
                    first_para = content.lstrip().split("\n\n")[0][:200]
                    desc = first_para.replace("#", "").strip()

                skill = SkillInfo(
                    name=skill_dir.name,
                    category=category_dir.name,
                    path=skill_dir,
                    description=desc[:300],
                    tags=[t for t in tags if t],
                    triggers=triggers[:10],
                    allowed_tools=allowed_tools,
                    size_chars=chars,
                    size_lines=lines,
                    estimated_tokens=max(chars // 4, 50),  # minimum 50 tokens
                    is_archived=is_archived,
                    has_frontmatter=fm_match is not None,
                    model=model,
                )

                result.skills.append(skill)

                if is_archived:
                    result.archived_tokens += skill.estimated_tokens
                else:
                    result.active_tokens += skill.estimated_tokens

            except Exception as e:
                result.errors.append(f"{skill_dir}: {e}")

    result.total_tokens = result.active_tokens + result.archived_tokens
    result.skills.sort(key=lambda s: s.estimated_tokens, reverse=True)
    return result