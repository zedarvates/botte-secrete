"""docs_steward — scoped documentation map for multi-component projects.

    from skills.docs_steward import build_map, write_indexes
    build_map("/path/to/monorepo")          # components + scoped docs, 0 tokens
    write_indexes("/path/to/monorepo")      # preview per-component DOCS.md (dry-run)
"""

from skills.docs_steward.steward import (
    build_map, detect_components, find_docs, render_index, write_indexes,
    Doc, Component, INDEX_FILENAME, INDEX_MARKER,
)

__all__ = ["build_map", "detect_components", "find_docs", "render_index",
           "write_indexes", "Doc", "Component", "INDEX_FILENAME", "INDEX_MARKER"]
