"""Docs steward — scoped documentation map for multi-component projects.

A monorepo (server + client + tools + …) accumulates docs at several scopes:
global docs at the root, and component docs inside each component's folder. When
an LLM coder is *bounded* to one component (e.g. the server), it should load only
that component's docs **plus links to the relevant global docs** — not every
other component's documentation. Loading the wrong scope wastes tokens every turn.

This builds that scoped map (0 cloud tokens, pure stdlib): detect components,
classify every doc as global or component-scoped, and — per component — produce a
ready-to-load index listing local docs + linked globals, with a token-cost
framing (full project docs vs the scoped load). `.md` is treated as LLM-facing
(load it); `.html` as human reference (linked, not loaded).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from skills.fallow_like.scanner import DEFAULT_IGNORE_DIRS
except Exception:  # keep usable even without fallow deps
    DEFAULT_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
                           "dist", "build", ".botte", ".pytest_cache"}

# Docs the LLM should read vs. docs for humans (rich, heavy → linked only).
LLM_DOC_EXTS = {".md", ".mdx", ".markdown", ".rst", ".txt"}
HUMAN_DOC_EXTS = {".html", ".htm"}
DOC_EXTS = LLM_DOC_EXTS | HUMAN_DOC_EXTS

# Top-level dirs whose *children* are the real components (monorepo containers).
CONTAINER_DIRS = {"apps", "packages", "services", "libs", "modules", "crates", "cmd"}
# Names that are components even before they hold much code.
COMPONENT_NAMES = {
    "server", "client", "frontend", "backend", "api", "web", "app", "mobile",
    "desktop", "worker", "gateway", "cli", "tools", "tool", "lib", "core",
    "shared", "common", "sdk", "daemon", "ui", "engine", "agent",
}
# Top-level dirs that are never a code component.
NON_COMPONENT_DIRS = {
    "docs", "doc", "documentation", "assets", "static", "public", "image",
    "images", "img", "media", "scripts", "examples", "example", "test", "tests",
    ".github", ".vscode", ".idea", "config", "configs", "fixtures",
} | DEFAULT_IGNORE_DIRS

MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml",
    "composer.json", "build.gradle", "pom.xml", "Gemfile", "tsconfig.json",
}
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".kt", ".lua",
    ".gd", ".zig", ".swift", ".scala",
}


def _est_tokens(chars: int) -> int:
    return max(1, chars // 4)


@dataclass
class Doc:
    path: str        # relative to project root (posix)
    fmt: str         # "md" | "html" | "other"
    audience: str    # "llm" | "human"
    chars: int
    tokens: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Component:
    name: str
    path: str        # relative to project root (posix)
    kind: str        # "manifest" | "convention" | "dir"
    local_docs: list = field(default_factory=list)
    linked_globals: list = field(default_factory=list)
    local_tokens: int = 0
    scoped_tokens: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["local_docs"] = [x.to_dict() if isinstance(x, Doc) else x for x in self.local_docs]
        return d


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def _doc_for(root: Path, p: Path) -> Doc:
    ext = p.suffix.lower()
    fmt = "md" if ext in LLM_DOC_EXTS else ("html" if ext in HUMAN_DOC_EXTS else "other")
    try:
        chars = len(p.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        chars = 0
    audience = "human" if ext in HUMAN_DOC_EXTS else "llm"
    return Doc(path=_rel(root, p), fmt=fmt, audience=audience,
               chars=chars, tokens=_est_tokens(chars))


def _has_manifest(d: Path) -> bool:
    return any((d / m).exists() for m in MANIFESTS)


def _has_code(d: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(d):
        dirnames[:] = [x for x in dirnames if x not in DEFAULT_IGNORE_DIRS]
        if any(Path(f).suffix.lower() in CODE_EXTS for f in filenames):
            return True
    return False


def _mk_component(root: Path, d: Path):
    name = d.name
    if _has_manifest(d):
        kind = "manifest"
    elif name.lower() in COMPONENT_NAMES:
        kind = "convention"
    elif _has_code(d):
        kind = "dir"
    else:
        return None
    return Component(name=name, path=_rel(root, d), kind=kind)


def detect_components(root: str | Path) -> list:
    """Top-level (and monorepo-container child) directories that are components."""
    root = Path(root).resolve()
    comps: list = []
    for entry in sorted(p for p in root.iterdir() if p.is_dir()):
        name = entry.name
        if name in NON_COMPONENT_DIRS:
            continue
        if name in CONTAINER_DIRS:
            for sub in sorted(p for p in entry.iterdir() if p.is_dir()):
                if sub.name in DEFAULT_IGNORE_DIRS:
                    continue
                c = _mk_component(root, sub)
                if c:
                    comps.append(c)
            continue
        c = _mk_component(root, entry)
        if c:
            comps.append(c)
    return comps


def find_docs(root: str | Path) -> list:
    """Every documentation file in the project (md/mdx/rst/txt/html)."""
    root = Path(root).resolve()
    docs: list = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in DEFAULT_IGNORE_DIRS]
        for fn in filenames:
            if Path(fn).suffix.lower() in DOC_EXTS:
                docs.append(_doc_for(root, Path(dirpath) / fn))
    return docs


def build_map(root: str | Path) -> dict:
    """Scoped documentation map: components + their docs, globals, token framing."""
    root = Path(root).resolve()
    components = detect_components(root)
    docs = find_docs(root)

    # Assign each doc to the deepest matching component, else it's global.
    comp_by_path = sorted(components, key=lambda c: len(c.path), reverse=True)
    global_docs: list = []
    for doc in docs:
        owner = None
        for c in comp_by_path:
            if doc.path == c.path or doc.path.startswith(c.path + "/"):
                owner = c
                break
        if owner is None:
            global_docs.append(doc)
        else:
            owner.local_docs.append(doc)

    global_tokens = sum(d.tokens for d in global_docs)
    # Globals worth linking from a component (LLM-facing only; html is human ref).
    linked = [d.path for d in global_docs if d.audience == "llm"]

    for c in components:
        c.local_docs.sort(key=lambda d: d.path)
        c.local_tokens = sum(d.tokens for d in c.local_docs)
        c.linked_globals = linked
        c.scoped_tokens = c.local_tokens + global_tokens

    total = sum(d.tokens for d in docs)
    return {
        "project": str(root),
        "components": [c.to_dict() for c in components],
        "global_docs": [d.to_dict() for d in global_docs],
        "global_tokens": global_tokens,
        "total_doc_tokens": total,
        "savings_note": (
            f"A coder bounded to one component loads its local docs + "
            f"{global_tokens} global tok, not all {total} project doc tok."),
    }


# ── per-component scoped index (DOCS.md) ─────────────────────────────────────

INDEX_MARKER = "<!-- botte-docs-steward -->"
INDEX_FILENAME = "DOCS.md"


def render_index(component: dict, project_root: str | Path) -> str:
    """Markdown a bounded LLM can load: local docs + links to global docs."""
    root = Path(project_root).resolve()
    comp_dir = root / component["path"]
    lines = [
        INDEX_MARKER,
        f"# {component['name']} — documentation scope",
        "",
        f"You are working in `{component['path']}/`. Load **these** docs; "
        "do not load other components' documentation.",
        "",
        "## Local docs (this component)",
    ]
    local = component.get("local_docs", [])
    if local:
        for d in local:
            link = os.path.relpath(root / d["path"], comp_dir).replace(os.sep, "/")
            tag = "" if d["audience"] == "llm" else " · _(html, human reference)_"
            lines.append(f"- [{Path(d['path']).name}]({link}) — ~{d['tokens']} tok{tag}")
    else:
        lines.append("- _(none yet)_")

    lines += ["", "## Global docs (shared — load only if relevant)"]
    gl = component.get("linked_globals", [])
    if gl:
        for gpath in gl:
            link = os.path.relpath(root / gpath, comp_dir).replace(os.sep, "/")
            lines.append(f"- [{Path(gpath).name}]({link})")
    else:
        lines.append("- _(none)_")

    lines += [
        "",
        f"_Scoped index by botte docs_steward · local ~{component.get('local_tokens', 0)} tok "
        f"· md = load, html = human reference._",
    ]
    return "\n".join(lines) + "\n"


def write_indexes(root: str | Path, *, dry_run: bool = True,
                  only: str | None = None) -> list:
    """Render (and optionally write) a DOCS.md per component. Confirm-gated.

    dry_run=True returns {component, path, content} without touching disk.
    """
    root = Path(root).resolve()
    m = build_map(root)
    results: list = []
    for c in m["components"]:
        if only and c["name"] != only:
            continue
        content = render_index(c, root)
        target = root / c["path"] / INDEX_FILENAME
        if not dry_run:
            target.write_text(content, encoding="utf-8")
        results.append({"component": c["name"],
                        "path": (target.relative_to(root)).as_posix(),
                        "written": not dry_run, "content": content})
    return results
