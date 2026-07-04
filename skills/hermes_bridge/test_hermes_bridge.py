"""Tests for hermes_bridge skill."""
from pathlib import Path
from skills.hermes_bridge.registry import SkillRegistry, get_registry, init_registry


def test_list_skills():
    registry = SkillRegistry()
    skills = registry.list_skills()
    assert isinstance(skills, list)
    assert "decision_ladder" in skills or "universal_compressor" in skills or "auto_memory" in skills


def test_get_registry_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is not None
    assert r1 is r2


def test_init_registry():
    registry = init_registry()
    assert len(registry._skills) > 0  # loaded some skills


def test_register_function():
    registry = SkillRegistry()
    fn = lambda x: x * 2
    registry.register_function("test_func", fn)
    assert registry.get_function("test_func") is not None
    assert registry.get_function("test_func")(5) == 10