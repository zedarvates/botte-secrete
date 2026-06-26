"""cwe_kb — local CWE knowledge base to enrich/de-noise security findings.

    from skills.cwe_kb import lookup, match, explain, enrich
    lookup("CWE-78")                  # exact entry, 0 tokens
    enrich(taint_findings)            # attach name/description/mitigation
"""

from skills.cwe_kb.kb import lookup, match, explain, enrich, load_catalog

__all__ = ["lookup", "match", "explain", "enrich", "load_catalog"]
