"""Directives Audit — find and validate the AI-agent guidance files in a project.

Different tools read different files (CLAUDE.md, AGENTS.md, .cursorrules,
copilot-instructions.md, GEMINI.md, .windsurfrules, …) and some teams keep
intent/spec docs in markdown *or* HTML. Before an agent works on a repo it
should know which directives exist, whether they are healthy, and — crucially —
whether they exist *at all*.

This module:
  1. Discovers agent-guidance, intent and spec files across known conventions
     and formats (markdown, plain text, HTML, mdc, yaml).
  2. Validates each: readable? oversized (burns context every turn)? references
     files that no longer exist? HTML where markdown is expected?
  3. Flags the big one — a project with NO agent directives at all — and
     recommends what to create.

Pure stdlib. Inspired by shadcn/improve's "recon" step (ingest intent docs so
decided tradeoffs aren't re-flagged) and ponytail's "least code" ethos.
"""

from __future__ import annotations

import html.parser
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ── Catalog of known directive / intent / spec files ─────────────────────────
# kind:  instructions = how the agent should behave (read every turn)
#        intent       = product/architecture decisions (read for context)
#        spec         = concrete specs/requirements
#        config       = machine-read agent config (json/yaml/toml)

@dataclass(frozen=True)
class Known:
    pattern: str        # path relative to project root (glob allowed)
    tool: str           # which agent/tool reads it
    kind: str           # instructions | intent | spec | config


CATALOG: tuple[Known, ...] = (
    # Claude Code
    Known("CLAUDE.md", "Claude Code", "instructions"),
    Known("CLAUDE.local.md", "Claude Code", "instructions"),
    Known(".claude/CLAUDE.md", "Claude Code", "instructions"),
    Known(".claude/settings.json", "Claude Code", "config"),
    Known(".claude/settings.local.json", "Claude Code", "config"),
    Known(".mcp.json", "Claude Code (MCP)", "config"),
    # OpenAI Codex / OpenCode / generic
    Known("AGENTS.md", "Codex / OpenCode / generic", "instructions"),
    Known(".agents/**/*.md", "generic agents", "instructions"),
    # Cursor
    Known(".cursorrules", "Cursor", "instructions"),
    Known(".cursor/rules/**/*.mdc", "Cursor", "instructions"),
    # GitHub Copilot
    Known(".github/copilot-instructions.md", "GitHub Copilot", "instructions"),
    Known(".github/instructions/**/*.instructions.md", "GitHub Copilot", "instructions"),
    # Gemini / Antigravity
    Known("GEMINI.md", "Gemini CLI", "instructions"),
    Known(".gemini/**/*.md", "Gemini CLI", "instructions"),
    Known("gemini-extension.json", "Gemini CLI", "config"),
    # Windsurf / Cline / Roo / Aider / Kilo
    Known(".windsurfrules", "Windsurf", "instructions"),
    Known(".clinerules", "Cline", "instructions"),
    Known(".clinerules/**/*.md", "Cline", "instructions"),
    Known(".roo/**/*.md", "Roo", "instructions"),
    Known(".aider.conf.yml", "Aider", "config"),
    Known("CONVENTIONS.md", "Aider / generic", "instructions"),
    # Intent / design docs (improve's recon set)
    Known("CONTEXT.md", "intent", "intent"),
    Known("DESIGN.md", "intent", "intent"),
    Known("PRODUCT.md", "intent", "intent"),
    Known("ARCHITECTURE.md", "intent", "intent"),
    Known("docs/adr/**/*.md", "intent (ADR)", "intent"),
    Known("docs/adr/**/*.html", "intent (ADR)", "intent"),
    # Specs
    Known("PRD.md", "spec", "spec"),
    Known("specs/**/*.md", "spec", "spec"),
    Known("specs/**/*.html", "spec", "spec"),
    Known("spec/**/*.md", "spec", "spec"),
    # HTML variants of instruction docs (some teams use HTML, not .md)
    Known("CLAUDE.html", "Claude Code (HTML!)", "instructions"),
    Known("AGENTS.html", "generic (HTML!)", "instructions"),
)

# Instruction files this size (tokens, est) are re-sent every turn → expensive.
INSTRUCTION_TOKEN_WARN = 2000
INSTRUCTION_TOKEN_CRIT = 5000


@dataclass
class DirectiveFile:
    path: str           # relative to project root
    tool: str
    kind: str
    fmt: str            # md | html | txt | json | yaml | mdc | other
    bytes: int
    tokens_est: int


@dataclass
class Finding:
    severity: str       # crit | err | warn | info
    path: str
    message: str
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Discovery ────────────────────────────────────────────────────────────────

def _fmt_of(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {
        "md": "md", "markdown": "md", "html": "html", "htm": "html",
        "txt": "txt", "text": "txt", "json": "json",
        "yml": "yaml", "yaml": "yaml", "mdc": "mdc",
    }.get(ext, "other")


def discover(project_root: Path) -> list[DirectiveFile]:
    """Find every catalogued directive/intent/spec file under project_root."""
    root = Path(project_root)
    seen: dict[str, DirectiveFile] = {}
    for known in CATALOG:
        for p in root.glob(known.pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if rel in seen:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            seen[rel] = DirectiveFile(
                path=rel, tool=known.tool, kind=known.kind,
                fmt=_fmt_of(p), bytes=size, tokens_est=max(1, size // 4),
            )
    return sorted(seen.values(), key=lambda d: (d.kind, d.path))


# ── HTML → text (stdlib, for reference-extraction on HTML directive docs) ─────

class _TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _read_text(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if _fmt_of(path) == "html":
        parser = _TextExtractor()
        try:
            parser.feed(raw)
            return parser.text()
        except Exception:
            return raw
    return raw


# Path-like references: backtick `path/to/file.ext` or bare a/b/c.ext tokens.
_REF_RE = re.compile(r"`([^`\n]+?)`|(?<![\w/])([\w./-]+\.[a-zA-Z0-9]{1,6})(?![\w/])")


def _extract_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for m in _REF_RE.finditer(text):
        token = (m.group(1) or m.group(2) or "").strip()
        # Drop URLs, commands, flags, home (~) and absolute/external paths.
        if not token or " " in token or token.startswith(("http", "#", "$", "-", "~", "/")):
            continue
        if "://" in token or token.endswith("/"):
            continue
        # Only treat tokens with a path separator as in-repo references; a bare
        # `name.ext` or extension like `.mapodc` is prose, not a path.
        if "/" not in token:
            continue
        refs.add(token.lstrip("/"))  # keep a leading "." (e.g. .claude/…) intact
    return refs


# ── Validation ────────────────────────────────────────────────────────────────

def validate(project_root: Path,
             files: Optional[list[DirectiveFile]] = None) -> list[Finding]:
    """Validate discovered directive files; return findings (worst first)."""
    root = Path(project_root)
    files = files if files is not None else discover(root)
    findings: list[Finding] = []

    instruction_files = [f for f in files if f.kind == "instructions"]

    # 1. No agent guidance at all — the big one.
    if not instruction_files:
        findings.append(Finding(
            "crit", ".",
            "No agent-instruction file found (CLAUDE.md / AGENTS.md / .cursorrules / …).",
            "Create CLAUDE.md (Claude Code) or AGENTS.md (broad compatibility) "
            "describing build/test/lint commands and conventions.",
        ))

    # 2. Multiple instruction sources — risk of drift/conflict.
    if len(instruction_files) >= 2:
        names = ", ".join(f.path for f in instruction_files)
        findings.append(Finding(
            "info", ".",
            f"Multiple instruction sources ({names}) — keep them consistent.",
            "Consider a single source of truth and link the others to it.",
        ))

    for f in files:
        p = root / f.path

        # 3. HTML where agents expect markdown.
        if f.kind == "instructions" and f.fmt == "html":
            findings.append(Finding(
                "warn", f.path,
                "Instruction file is HTML — most agents parse markdown best.",
                "Convert to markdown (.md); keep HTML only if a tool requires it.",
            ))

        # 4. Oversized instruction file (re-sent every turn).
        if f.kind == "instructions":
            if f.tokens_est >= INSTRUCTION_TOKEN_CRIT:
                findings.append(Finding(
                    "err", f.path,
                    f"Instruction file is large (~{f.tokens_est} tok) — sent every turn.",
                    "Trim to essentials; move reference material into linked docs.",
                ))
            elif f.tokens_est >= INSTRUCTION_TOKEN_WARN:
                findings.append(Finding(
                    "warn", f.path,
                    f"Instruction file is ~{f.tokens_est} tok — watch the per-turn cost.",
                    "Aim under ~2000 tokens for always-on instructions.",
                ))

        # 5. Empty / unreadable.
        text = _read_text(p)
        if f.kind in ("instructions", "intent", "spec") and not text.strip():
            findings.append(Finding(
                "warn", f.path, "File is empty or unreadable.",
                "Remove it or fill it in — an empty directive misleads agents.",
            ))
            continue

        # 6. Broken in-repo references (prose docs only — config files hold
        #    permission domains, mime types etc. that look like paths but aren't).
        if f.kind == "config" or f.fmt not in ("md", "txt", "html", "mdc"):
            continue
        missing = []
        for ref in sorted(_extract_refs(text)):
            # Resolve relative to root and to the file's own dir.
            if (root / ref).exists() or (p.parent / ref).exists():
                continue
            # Ignore obviously-external or placeholder tokens.
            if ref.count(".") == 1 and "/" not in ref and len(ref) <= 8:
                continue  # e.g. "e.g", "etc." style false hits already filtered
            missing.append(ref)
        if missing:
            shown = ", ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
            findings.append(Finding(
                "warn", f.path,
                f"References {len(missing)} path(s) not found in repo: {shown}",
                "Update or remove stale references so agents don't chase dead paths.",
            ))

    order = {"crit": 0, "err": 1, "warn": 2, "info": 3}
    return sorted(findings, key=lambda x: order.get(x.severity, 9))


# ── Top-level report ─────────────────────────────────────────────────────────

def audit(project_root: str | Path) -> dict:
    """Full directives audit for a project."""
    root = Path(project_root)
    files = discover(root)
    findings = validate(root, files)
    by_kind: dict[str, int] = {}
    for f in files:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
    return {
        "project": str(root),
        "has_instructions": any(f.kind == "instructions" for f in files),
        "files_found": len(files),
        "by_kind": by_kind,
        "files": [asdict(f) for f in files],
        "findings": [f.to_dict() for f in findings],
        "score": _score(findings),
    }


def _score(findings: list[Finding]) -> int:
    """0-100 directive-health score (100 = clean)."""
    score = 100
    weights = {"crit": 40, "err": 15, "warn": 5, "info": 0}
    for f in findings:
        score -= weights.get(f.severity, 0)
    return max(0, score)
