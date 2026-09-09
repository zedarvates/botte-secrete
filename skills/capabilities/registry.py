"""Capability registry — the system's model of itself (the curator's data).

Scans every `SKILL.md` and builds a tree of capabilities organised into the
system's layers (SENSE → DECIDE → ACT → REMEMBER → GOVERN → DEPLOY). This is the
arborescence the Conductor reads to compose a plan, and the "curator" uses to
pick the right capability for a goal.

A skill's layer comes from a `layer:` frontmatter field if present, else the map
below, else ACT. Pure stdlib.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

LAYERS = ["SENSE", "DECIDE", "ACT", "REMEMBER", "GOVERN", "DEPLOY"]

# Layer per skill folder (override with `layer:` in the SKILL.md frontmatter).
LAYER_MAP = {
    # SENSE — understand project / cluster / task
    "directives_audit": "SENSE", "metrics": "SENSE", "infra_advisor": "SENSE",
    "fallow_like": "SENSE", "skill_finder": "SENSE", "llm_backends": "SENSE",
    "understand-anything": "SENSE",
    # DECIDE — route the work, cheapest capable
    "auto_router": "DECIDE", "tiered_router": "DECIDE", "local_router": "DECIDE",
    "preflight": "DECIDE", "monte_cristo": "DECIDE",
    # ACT — do the work, local-first
    "llm_mcp": "ACT", "ingest": "ACT", "docgen": "ACT", "app_test": "ACT",
    "prompt_improver": "ACT", "mousquetaires": "ACT", "cardinal": "ACT",
    "simplify-code": "ACT", "media_loader": "ACT",
    # REMEMBER — capitalise
    "response_cache": "REMEMBER", "code_fingerprint": "REMEMBER",
    "hermes-second-brain": "REMEMBER", "vector_protocol": "REMEMBER",
    "ultra_compact": "REMEMBER", "loader": "REMEMBER", "cache": "REMEMBER",
    "diff_language": "REMEMBER",
    # GOVERN — consistency & cost
    "clarification": "GOVERN", "checkup": "GOVERN", "dashboard": "GOVERN",
    "skill_project_optimizer": "GOVERN",
    "code-rules": "GOVERN", "karpathy-guidelines": "GOVERN",
    # DEPLOY — wire & measure
    "bootstrap": "DEPLOY",
}

# Capabilities that can reach a cloud model (everything else is local-only).
_CLOUD_CAPABLE = {
    "auto_router", "tiered_router", "docgen", "mousquetaires", "cardinal",
    "monte_cristo",
}


@dataclass
class Capability:
    name: str
    layer: str
    description: str
    path: str
    local_capable: bool
    effects: Optional[dict] = None

    def to_dict(self) -> dict:
        result = asdict(self)
        if self.effects is None:
            result.pop("effects")  # preserve the legacy discovery contract
        return result


def _frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip()
    return fm, m.group(2)


def _summary(name: str, fm: dict, body: str) -> str:
    if fm.get("description"):
        return fm["description"]
    for line in body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.startswith(("```", "|", "-")):
            return s[:200]
    return name


def load(skills_root: Optional[Path] = None, *,
         include_effects: bool = False, preserve_paths: bool = False,
         capability_namespace: Optional[str] = None) -> list[Capability]:
    """Discover skills; effects-aware callers retain every path.

    For external trees, supply a trusted namespace such as owner/repo:skills.
    preserve_paths keeps collisions visible without reading any sidecars.
    """
    root = Path(skills_root or (REPO_ROOT / "skills")).resolve()
    caps: dict[str, Capability] = {}
    for md in sorted(root.rglob("SKILL.md")):
        folder = md.parent.name
        key = md.as_posix() if include_effects or preserve_paths else folder
        if key in caps:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, body = _frontmatter(text)
        name = fm.get("name") or folder
        layer = (fm.get("layer") or LAYER_MAP.get(folder) or "ACT").upper()
        if layer not in LAYERS:
            layer = "ACT"
        try:
            rel = md.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = md.as_posix()  # scanning a tree outside the repo
        effects = None
        if include_effects:
            from skills.capabilities.effects import inspect_effects
            expected_id = (capability_namespace + "/" + md.parent.relative_to(root).as_posix()
                           if capability_namespace is not None else None)
            effects = inspect_effects(md.parent, expected_id=expected_id)
        caps[key] = Capability(
            name=name, layer=layer, description=_summary(name, fm, body),
            path=rel, local_capable=folder not in _CLOUD_CAPABLE,
            effects=effects,
        )
    return sorted(caps.values(), key=lambda c: (LAYERS.index(c.layer), c.name, c.path))


def by_layer(caps: Optional[list[Capability]] = None) -> dict[str, list[Capability]]:
    caps = caps if caps is not None else load()
    out: dict[str, list[Capability]] = {ly: [] for ly in LAYERS}
    for c in caps:
        out.setdefault(c.layer, []).append(c)
    return out


_LAYER_TAG = {
    "SENSE": "understand project / cluster / task",
    "DECIDE": "route the work, cheapest capable",
    "ACT": "do the work, local-first",
    "REMEMBER": "capitalise (compounding)",
    "GOVERN": "consistency & cost control",
    "DEPLOY": "wire into projects & measure",
}


def ascii_map(caps: Optional[list[Capability]] = None) -> str:
    grouped = by_layer(caps)
    lines = ["botte-secrète  (the system)", "│"]
    for i, layer in enumerate(LAYERS):
        members = grouped.get(layer, [])
        if not members:
            continue
        last_layer = i == len(LAYERS) - 1
        branch = "└─" if last_layer else "├─"
        lines.append(f"{branch} {layer} — {_LAYER_TAG[layer]}")
        pipe = "   " if last_layer else "│  "
        names = ", ".join(c.name + ("" if c.local_capable else "↑") for c in members)
        lines.append(f"{pipe}   {names}")
    lines.append("")
    lines.append("↑ = can escalate to a cloud model; everything else is local-first.")
    return "\n".join(lines)


def curate(goal: str, caps: Optional[list[Capability]] = None, top_k: int = 5,
           *, include_paths: bool = False) -> list[dict]:
    """Pick relevant capabilities; opt into paths for unambiguous association."""
    caps = caps if caps is not None else load()
    try:
        from skills.skill_finder.finder import _tokens, _fuzzy_hit
    except ImportError:
        scored = [(0.0, c) for c in caps]
    else:
        q = _tokens(goal)
        scored = []
        for c in caps:
            words = _tokens(c.name + " " + c.description)
            s = sum(_fuzzy_hit(w, words) for w in q) / (len(q) or 1)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
    return [{"name": c.name, "layer": c.layer, "score": round(s, 3),
             "local_capable": c.local_capable, "why": c.description[:120],
             **({"path": c.path} if include_paths else {})}
            for s, c in scored[:top_k]]
