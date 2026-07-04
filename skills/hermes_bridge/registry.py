"""
Skill Registry — auto-discover and load skills from the skills/ directory.

Usage:
    from skills.hermes_bridge.registry import SkillRegistry
    registry = SkillRegistry()
    registry.load_all()
    skill = registry.get("decision_ladder")
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

SKILLS_DIR = Path(__file__).parent.parent


class SkillRegistry:
    """Registry for botte-secrete skills."""

    def __init__(self, skills_dir: Path | None = None):
        self.base = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._skills: dict[str, Any] = {}
        self._functions: dict[str, Callable] = {}

    def load_skill(self, name: str) -> Any:
        """Load a skill module by name."""
        if name in self._skills:
            return self._skills[name]

        skill_path = self.base / name
        if not skill_path.exists():
            raise ValueError(f"Skill '{name}' not found at {skill_path}")

        # Load module
        spec = importlib.util.spec_from_file_location(f"skills.{name}", skill_path / "__init__.py")
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"skills.{name}"] = module
            spec.loader.exec_module(module)
            self._skills[name] = module
            return module

        raise ValueError(f"Could not load skill '{name}'")

    def get(self, name: str) -> Any:
        """Get a loaded skill or load it."""
        if name not in self._skills:
            self.load_skill(name)
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """List available skill names."""
        if not self.base.exists():
            return []
        return [d.name for d in self.base.iterdir() if d.is_dir() and (d / "__init__.py").exists()]

    def register_function(self, name: str, func: Callable):
        """Register a helper function."""
        self._functions[name] = func

    def get_function(self, name: str) -> Callable | None:
        """Get a registered function."""
        return self._functions.get(name)

    def auto_load(self):
        """Load all discovered skills."""
        for name in self.list_skills():
            try:
                self.load_skill(name)
            except Exception as e:
                print(f"Warning: Could not load skill {name}: {e}")


# Global registry instance
_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def init_registry() -> SkillRegistry:
    global _registry
    _registry = SkillRegistry()
    _registry.auto_load()
    return _registry