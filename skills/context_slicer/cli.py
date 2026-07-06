"""Context Slicer — segmentation du contexte en fenêtres indépendantes.

Permet le chargement sélectif par agent et par type de tâche.
Chaque "slice" est un bloc de contexte indépendant qui peut être
chargé ou ignoré selon les besoins.

Usage:
    python -m skills.context_slicer.cli slice < fichier.txt --windows 3
    python -m skills.context_slicer.cli select "query" --type audit
    python -m skills.context_slicer.cli stats
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ContextSlice:
    """A single context slice."""
    id: str
    title: str
    content: str
    slice_type: str  # "code", "doc", "config", "log", "result", "meta"
    token_count: int = 0
    priority: int = 5  # 1-10, plus haut = plus important
    task_types: list[str] = field(default_factory=lambda: ["all"])

    def __post_init__(self):
        self.token_count = len(self.content) // 4


# ── Section markers — délimiteurs de slices ────────────────────

SLICE_MARKERS = [
    (r'^#{1,3}\s+(.+)$',                   "doc"),       # Markdown headings
    (r'^//\s*={3,}\s*(.+)\s*={3,}\s*$',    "code"),      # // === title ===
    (r'^#\s*={3,}\s*(.+)\s*={3,}\s*$',     "code"),      # # === title ===
    (r'^```(\w*)',                          "code"),      # Code blocks
    (r'^%%%\s*(.+)$',                       "meta"),      # %%% metadata
    (r'^;;;\s*(.+)$',                       "config"),    # ;;; config
]


def detect_slices(content: str) -> list[ContextSlice]:
    """Detect context slices from content structure."""
    slices = []
    lines = content.split("\n")
    current_slice = None
    current_lines = []
    slice_id = 0

    def _flush():
        nonlocal slice_id
        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                slices.append(ContextSlice(
                    id=f"slice_{slice_id}",
                    title=current_title or f"Section {slice_id}",
                    content=text,
                    slice_type=current_type or "doc",
                ))
                slice_id += 1

    current_title = ""
    current_type = "doc"
    in_code_block = False

    for line in lines:
        # Track code blocks
        if line.startswith("```"):
            if in_code_block:
                _flush()
                in_code_block = False
                current_lines = []
                current_title = ""
                current_type = "doc"
                continue
            else:
                _flush()
                in_code_block = True
                current_lines = [line]
                current_title = line[3:].strip() or "code block"
                current_type = "code"
                continue

        if in_code_block:
            current_lines.append(line)
            continue

        # Check for slice markers
        matched = False
        for pattern, stype in SLICE_MARKERS:
            m = re.match(pattern, line)
            if m:
                _flush()
                current_lines = [line]
                current_title = (m.group(1) if m.lastindex and m.group(1) else "").strip()
                current_type = stype
                matched = True
                break

        if not matched:
            current_lines.append(line)

    _flush()  # Don't forget the last section

    return slices


def select_slices(slices: list[ContextSlice], query: str,
                  max_tokens: int = 2000,
                  task_type: str = "all") -> list[ContextSlice]:
    """Select the most relevant slices for a given query."""
    query_words = set(query.lower().split())
    scored = []

    for s in slices:
        if task_type != "all" and task_type not in s.task_types:
            continue

        # Relevance score: word overlap with query
        content_words = set(s.content.lower().split())
        overlap = len(query_words & content_words)
        relevance = overlap / max(len(query_words), 1)

        # Final score: relevance + priority bonus
        score = relevance * 0.7 + (s.priority / 10) * 0.3
        scored.append((score, s))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Select best slices within token budget
    selected = []
    total_tokens = 0
    for score, s in scored:
        if total_tokens + s.token_count <= max_tokens:
            selected.append(s)
            total_tokens += s.token_count

    return selected


def cmd_slice(args):
    """Slice content into windows."""
    content = Path(args.input).read_text() if args.input else sys.stdin.read()
    slices = detect_slices(content)

    print(f"Detected {len(slices)} slices:")
    for s in slices[:10]:
        print(f"  [{s.slice_type}] {s.title} ({s.token_count} tok)")
    if len(slices) > 10:
        print(f"  ... and {len(slices) - 10} more")

    if args.output:
        output = []
        for i, s in enumerate(slices):
            output.append(f"# SLICE {i}: [{s.slice_type}] {s.title}")
            output.append(f"# Tokens: {s.token_count}")
            output.append(s.content)
            output.append("")
        Path(args.output).write_text("\n".join(output))


def cmd_select(args):
    """Select slices relevant to a query."""
    content = Path(args.input).read_text() if args.input else sys.stdin.read()
    slices = detect_slices(content)
    selected = select_slices(slices, args.query, args.budget, args.type)

    print(f"Selected {len(selected)}/{len(slices)} slices ({args.budget} tok budget):")
    print()
    for s in selected:
        print(f"--- [{s.slice_type}] {s.title} ---")
        print(s.content[:200])
        if len(s.content) > 200:
            print("...")
        print()


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="context_slicer", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("slice", help="Slice content")
    s.add_argument("--input", help="Input file (stdin)")
    s.add_argument("--output", help="Output file")
    s.set_defaults(func=cmd_slice)

    s2 = sub.add_parser("select", help="Select relevant slices")
    s2.add_argument("query", help="Query to match")
    s2.add_argument("--input", help="Input file (stdin)")
    s2.add_argument("--budget", type=int, default=2000, help="Token budget")
    s2.add_argument("--type", default="all", help="Task type filter")
    s2.set_defaults(func=cmd_select)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
