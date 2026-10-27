"""Ordering helper for the BUILDER -> MIGRATION_AUDIT -> VALIDATOR gate."""

from __future__ import annotations


def _name(value: object) -> str:
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def insert_migration_audit_stage(stages: list[str]) -> list[str]:
    """Insert the audit exactly once between BUILDER and VALIDATOR."""
    if not isinstance(stages, list) or not stages or not all(isinstance(item, str) for item in stages):
        raise ValueError("stages must be a non-empty list of names")
    names = [_name(item) for item in stages]
    if names.count("BUILDER") != 1 or names.count("VALIDATOR") != 1:
        raise ValueError("migration pipeline requires exactly one BUILDER and one VALIDATOR")
    builder = names.index("BUILDER")
    validator = names.index("VALIDATOR")
    if builder >= validator:
        raise ValueError("BUILDER must precede VALIDATOR")
    audits = [index for index, name in enumerate(names) if name == "MIGRATION_AUDIT"]
    if len(audits) > 1:
        raise ValueError("MIGRATION_AUDIT must appear at most once")
    if audits:
        if not builder < audits[0] < validator:
            raise ValueError("MIGRATION_AUDIT must be between BUILDER and VALIDATOR")
        return list(stages)
    return [*stages[:validator], "MIGRATION_AUDIT", *stages[validator:]]


__all__ = ["insert_migration_audit_stage"]
