"""Dead code detection using AST analysis — with sensible exclusions."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult, Symbol
from skills.fallow_like.models import DeadCodeFinding, Severity
from collections import defaultdict


# ── Common library entry points — never flag these as dead ──
ALIVE_NAMES = {
    # Python magic
    "__init__", "__new__", "__call__", "__getitem__", "__setitem__",
    "__iter__", "__next__", "__enter__", "__exit__", "__repr__", "__str__",
    "__eq__", "__hash__", "__len__", "__bool__", "__contains__",
    "__add__", "__sub__", "__mul__", "__truediv__", "__getattr__", "__setattr__",
    # Common entry points
    "main", "run", "setup", "create_app", "index", "handler",
    "router", "middleware", "configure", "initialize",
    # Common patterns
    "get_", "create_", "build_", "make_", "from_", "to_", "parse_", "encode_",
    "decode_", "load_", "save_", "read_", "write_", "fetch_", "send_",
    # CLI
    "cli", "app", "command", "callback",
    # Testing
    "test_", "fixture", "conftest",
    # Framework override callbacks (called by the framework, not by name)
    "do_", "handle_", "visit_", "on_", "activate", "deactivate",
    "log_message", "emit", "format", "flush", "close",
}


# ── Files that should never be scanned for dead code ──
SKIP_FILES = {"__init__.py", "setup.py", "conftest.py"}


class DeadCodeAnalyzer:
    """Detects unused symbols with smarter exclusions."""

    def __init__(self, min_confidence: float = 0.8):
        self.min_confidence = min_confidence

    def _is_alive_name(self, name: str) -> bool:
        """Check if name matches a known-alive pattern."""
        if name in ALIVE_NAMES:
            return True
        for pattern in ALIVE_NAMES:
            if pattern.endswith("_") and name.startswith(pattern):
                return True
        return False

    def _get_file_imports(self, scan: ScanResult) -> dict[str, set[str]]:
        """Build map: file → set of files it imports from."""
        file_imports: dict[str, set[str]] = {}
        for file_ast in scan.files:
            imported_files = set()
            for imp in file_ast.imports:
                # Extract module path from import statement
                parts = imp.replace("import ", "").replace("from ", "").split()
                for p in parts:
                    p = p.strip().strip(",").strip(";")
                    if p and p not in ("*", "as", "."):
                        imported_files.add(p.replace(".", "/") + ".py")
            file_imports[file_ast.path] = imported_files
        return file_imports

    def _is_imported_by_others(self, filepath: str,
                               file_imports: dict[str, set[str]]) -> bool:
        """Check if this file is imported by any other file."""
        for importer, imports in file_imports.items():
            if importer == filepath:
                continue
            if filepath in imports:
                return True
            # Also check partial matches (e.g., 'turboquant/db.py' vs 'turboquant.db')
            base = filepath.replace("/", ".").replace(".py", "")
            for imp in imports:
                if imp.endswith(base) or base.endswith(imp.replace(".py", "")):
                    return True
        return False

    def _name_occurrences(self, scan: ScanResult) -> dict:
        """Count every identifier occurrence across all source (strings included).

        Catches dynamic usage a static import graph misses: MCP dispatch tables
        ({"find_skills": _tool_find_skills}), `__all__` re-exports, getattr and
        other string-keyed dispatch. A symbol referenced beyond its own
        definition is alive.
        """
        import re
        token = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*")
        occ: dict[str, int] = defaultdict(int)
        for file_ast in scan.files:
            for m in token.finditer(file_ast.source or b""):
                occ[m.group().decode("ascii", "ignore")] += 1
        return occ

    def analyze(self, scan: ScanResult) -> list:
        findings = []
        definitions: dict[str, list[tuple[str, Symbol]]] = defaultdict(list)
        usages: dict[str, int] = defaultdict(int)
        file_imports = self._get_file_imports(scan)
        occ = self._name_occurrences(scan)

        for file_ast in scan.files:
            filename = file_ast.path.split("/")[-1]

            # Skip special files
            if filename in SKIP_FILES:
                continue

            for sym in file_ast.symbols:
                if sym.type in ("function", "class", "variable"):
                    definitions[sym.name].append((file_ast.path, sym))

            # Count usages from imports
            for imp in file_ast.imports:
                parts = imp.replace("import ", "").replace("from ", "").split()
                for p in parts:
                    p = p.strip().strip(",").strip(";")
                    if p and p not in ("*", "as"):
                        usages[p] += 1

            # Count usages from exports
            for exp in file_ast.exports:
                usages[exp] += 1

        for name, locations in definitions.items():
            usage_count = usages.get(name, 0)

            # Skip known-alive names
            if self._is_alive_name(name):
                continue

            # Referenced anywhere beyond its own definition(s) → alive. Each
            # definition contributes one occurrence of the name; more than that
            # means it's used somewhere (call, dispatch table, __all__, …).
            if occ.get(name, 0) > len(locations):
                continue

            for fpath, sym in locations:
                filename = fpath.split("/")[-1]

                # Skip test files — vars used by test framework
                if "test" in filename.lower() or "spec" in filename.lower():
                    usage_count += 1
                    continue

            # If file is imported by others, symbols might be used externally
            # (Can't prove they're dead without full call graph)
            if usage_count == 0:
                for fpath, sym in locations:
                    if self._is_imported_by_others(fpath, file_imports):
                        # File is imported — symbol COULD be used externally
                        # Only flag with low confidence
                        findings.append(DeadCodeFinding(
                            rule_id="DEAD001",
                            severity=Severity.WARNING,
                            message=f"Possibly unused {sym.type} '{name}' (file is imported)",
                            file=fpath, line=sym.line, column=sym.column,
                            end_line=sym.end_line,
                            symbol_type=sym.type, symbol_name=name,
                            references_found=0,
                            confidence=0.5,  # Low — could be external
                            fix_hint=f"Verify if '{name}' is used externally before removing",
                        ))
                    else:
                        # File NOT imported — symbol likely dead
                        findings.append(DeadCodeFinding(
                            rule_id="DEAD001",
                            severity=Severity.WARNING,
                            message=f"Unused {sym.type} '{name}' — no importers found",
                            file=fpath, line=sym.line, column=sym.column,
                            end_line=sym.end_line,
                            symbol_type=sym.type, symbol_name=name,
                            references_found=0,
                            confidence=0.85,  # Higher — no importers
                            fix_hint=f"Remove unused {sym.type} '{name}' or export it",
                        ))

        return findings
