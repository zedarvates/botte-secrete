"""directives_audit — find & validate AI-agent guidance files in any project.

    from skills.directives_audit import audit
    report = audit("/path/to/project")

Detects CLAUDE.md, AGENTS.md, .cursorrules, copilot-instructions.md, GEMINI.md,
intent docs (CONTEXT/DESIGN/PRODUCT/ADR) and specs — in markdown, text or HTML —
then flags missing, oversized, HTML-instead-of-markdown, empty, and stale-
reference issues.
"""

from skills.directives_audit.directives import (
    audit, discover, validate, CATALOG, DirectiveFile, Finding,
)
from skills.directives_audit.rules import audit_rules, rule_semantic_sha256

__all__ = [
    "audit", "audit_rules", "discover", "validate", "rule_semantic_sha256",
    "CATALOG", "DirectiveFile", "Finding",
]
