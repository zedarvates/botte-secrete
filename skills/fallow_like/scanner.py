"""Multi-language AST scanner using tree-sitter."""

from __future__ import annotations
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_rust as tsrust
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Node
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


LANG_MAP = {
    ".py": ("python", tspython.language()),
    ".js": ("javascript", tsjs.language()),
    ".jsx": ("javascript", tsjs.language()),
    ".ts": ("typescript", tsts.language_typescript()),
    ".tsx": ("typescript", tsts.language_tsx()),
    ".rs": ("rust", tsrust.language()),
    ".go": ("go", tsgo.language()),
    ".java": ("java", tsjava.language()),
    ".c": ("c", tsc.language()),
    ".h": ("c", tsc.language()),
    ".cpp": ("cpp", tscpp.language()),
    ".hpp": ("cpp", tscpp.language()),
}

SYMBOL_TYPES = {
    "function_definition": "function",
    "function_declaration": "function",
    "method_definition": "function",
    "class_definition": "class",
    "class_declaration": "class",
    "interface_declaration": "class",
    "variable_declaration": "variable",
    "import_statement": "import",
    "import_from_statement": "import",
    "import_declaration": "import",
}


@dataclass
class Symbol:
    name: str
    type: str
    file: str
    line: int
    column: int
    end_line: int
    node_type: str = ""


@dataclass
class FileAST:
    path: str
    language: str
    source: bytes
    tree: object = None
    symbols: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    exports: list = field(default_factory=list)


@dataclass
class ScanResult:
    files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# Directories never worth scanning — vendored deps, build output, VCS, caches,
# git worktrees and archive copies. Skipped by default so the scanner works
# out-of-the-box on large, multi-component projects without hanging.
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", "bower_components", "vendor", "third_party",
    "dist", "build", "out", "target", "bin", "obj",
    ".kilo", ".kilocode", "worktrees", "Archives", ".archive",
    ".botte", ".botte-cache", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".cache", ".gradle", ".next", ".nuxt", ".turbo", "coverage", ".godot",
}

DEFAULT_MAX_FILES = 4000  # safety cap so a pathological tree can't hang the scan


class ProjectScanner:
    def __init__(self, root: str, ignore_patterns: list[str] | None = None,
                 max_files: int = DEFAULT_MAX_FILES):
        self.root = Path(root).resolve()
        self.ignore = ignore_patterns or []
        self.max_files = max_files
        self._parsers: dict[str, Parser] = {}

    def _get_parser(self, lang: str, lang_func) -> Parser:
        if lang not in self._parsers:
            parser = Parser(Language(lang_func))
            self._parsers[lang] = parser
        return self._parsers[lang]

    def _should_ignore(self, path: Path) -> bool:
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return True
        # Skip anything inside a default-ignored directory (no descent cost: we
        # still iterate but reject fast on the path parts).
        if any(part in DEFAULT_IGNORE_DIRS for part in parts):
            return True
        rel = "/".join(parts)
        return any(pattern in rel for pattern in self.ignore)

    def scan(self) -> ScanResult:
        result = ScanResult()
        lang_counts: dict[str, int] = {}
        total_lines = 0
        capped = False

        import os
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories in place so we never descend into
            # node_modules/.venv/etc. (huge perf win on real projects).
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS]
            if capped:
                break
            for fname in filenames:
                if len(result.files) >= self.max_files:
                    capped = True
                    break
                fpath = Path(dirpath) / fname
                if self._should_ignore(fpath):
                    continue

                ext = fpath.suffix
                if ext not in LANG_MAP:
                    continue

                lang, lang_func = LANG_MAP[ext]

                try:
                    source = fpath.read_bytes()
                    parser = self._get_parser(lang, lang_func)
                    tree = parser.parse(source)

                    rel_path = str(fpath.relative_to(self.root))
                    file_ast = FileAST(
                        path=rel_path,
                        language=lang,
                        source=source,
                        tree=tree,
                    )

                    self._extract_symbols(file_ast, tree.root_node)
                    self._extract_imports(file_ast, tree.root_node)
                    self._extract_exports(file_ast, tree.root_node)

                    result.files.append(file_ast)
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                    total_lines += source.count(b"\n") + 1

                except Exception as e:
                    result.errors.append(f"{fpath}: {e}")

        result.stats = {
            "total_files": len(result.files),
            "total_lines": total_lines,
            "languages": lang_counts,
            "capped": capped,
            "max_files": self.max_files,
        }
        if capped:
            result.errors.append(
                f"scan capped at {self.max_files} files — pass a higher max_files "
                "or add ignore_patterns to scan the rest.")
        return result

    def _extract_symbols(self, file_ast: FileAST, node: Node, depth: int = 0):
        if node.type in SYMBOL_TYPES:
            name = self._get_node_name(node, file_ast.source)
            if name:
                file_ast.symbols.append(Symbol(
                    name=name,
                    type=SYMBOL_TYPES[node.type],
                    file=file_ast.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    end_line=node.end_point[0] + 1,
                    node_type=node.type,
                ))

        for child in node.children:
            self._extract_symbols(file_ast, child, depth + 1)

    def _get_node_name(self, node: Node, source: bytes) -> str:
        for child in node.children:
            if child.type in ("identifier", "name"):
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return ""

    def _extract_imports(self, file_ast: FileAST, node: Node):
        if node.type in ("import_statement", "import_from_statement", "import_declaration"):
            text = file_ast.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            file_ast.imports.append(text.strip())
        for child in node.children:
            self._extract_imports(file_ast, child)

    def _extract_exports(self, file_ast: FileAST, node: Node):
        if node.type in ("export_statement", "export_declaration", "export_default_declaration"):
            name = self._get_node_name(node, file_ast.source)
            if name:
                file_ast.exports.append(name)
        for child in node.children:
            self._extract_exports(file_ast, child)