"""Zero-token trigger evaluation for the Monte Cristo outsider agent."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TriggerContext:
    """Caller-observed context that cannot always be inferred from one prompt."""

    material_consequence: bool = False
    blue_red_stalled: bool = False
    inherited_frame: bool = False
    routine_scope: bool = False


@dataclass(frozen=True)
class TriggerDecision:
    """Deterministic, auditable dispatch decision."""

    invoke: bool
    score: int
    threshold: int
    signals: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["signals"] = list(self.signals)
        return data


_THRESHOLD = 4
_EXPLICIT = re.compile(
    r"\b(?:monte[\s_-]*cristo|comte\s+de\s+monte[\s-]*cristo|"
    r"strategic\s+outsider|agent\s+outsider)\b",
    re.IGNORECASE,
)
_ROUTINE = re.compile(
    r"\b(?:typo|faute\s+d['’]orthographe|petite?\s+correction|one[ -]line\s+fix|"
    r"small\s+bug|routine\s+(?:review|revue)|revue\s+ordinaire|"
    r"review\s+this\s+(?:small\s+)?function|test\s+unitaire\s+isol[ée])\b",
    re.IGNORECASE,
)
_NON_AGENT_REFERENCE = re.compile(
    r"(?:\b(?:r[ée]sum[ée]|summari[sz]e|summary|analyse\s+litt[ée]raire|book\s+report|"
    r"roman|novel|livre|book|film|movie|sandwich|recette|recipe)\b.{0,60}\bmonte[\s-]*cristo\b|"
    r"\bmonte[\s-]*cristo\b.{0,60}\b(?:roman|novel|livre|book|film|movie|sandwich|"
    r"recette|recipe|chapter|chapitre)\b)",
    re.IGNORECASE,
)

_SIGNAL_RULES: tuple[tuple[str, int, re.Pattern[str]], ...] = (
    (
        "strategic_reset",
        2,
        re.compile(
            r"\b(?:strategic\s+reset|architecture\s+reset|remise\s+[àa]\s+plat|"
            r"repartir\s+de\s+z[ée]ro|rethink\s+(?:the\s+)?architecture|"
            r"faut[ -]il\s+(?:encore\s+)?(?:garder|conserver|remplacer|abandonner)|"
            r"should\s+we\s+(?:keep|replace|retire)|direction\s+de\s+recherche|"
            r"research\s+direction|programme\s+de\s+recherche)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "inherited_frame",
        2,
        re.compile(
            r"\b(?:inherited\s+assumptions?|hypoth[eè]ses?\s+h[ée]rit[ée]es?|"
            r"inherited\s+(?:architecture|system|platform|design)|"
            r"(?:architecture|syst[eè]me|plateforme|conception)\s+h[ée]rit[ée]e|"
            r"pr[ée]misses?\s+h[ée]rit[ée]es?|sunk\s+cost|co[uû]ts?\s+irr[ée]cup[ée]rables?|"
            r"sacred\s+cow|vache\s+sacr[ée]e|dogme|m[eê]me\s+cadre|same\s+frame|"
            r"habitudes?\s+historiques?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "blue_red_stalemate",
        2,
        re.compile(
            r"(?:\b(?:blue|bleue?)\s+team\b.{0,80}\b(?:red|rouge)\s+team\b|"
            r"\b(?:red|rouge)\s+team\b.{0,80}\b(?:blue|bleue?)\s+team\b|"
            r"\b(?:blue\s+and\s+red|red\s+and\s+blue)\s+teams?\b|"
            r"\b[ée]quipes?\s+(?:bleue\s+et\s+rouge|rouge\s+et\s+bleue)\b|"
            r"\b[ée]quipe\s+bleue\b.{0,80}\b[ée]quipe\s+rouge\b|"
            r"\b[ée]quipe\s+rouge\b.{0,80}\b[ée]quipe\s+bleue\b|"
            r"\baudit\b.{0,40}\bcontre[ -]?audit\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "material_consequence",
        1,
        re.compile(
            r"\b(?:irreversible|irr[ée]versible|major\s+migration|migration\s+majeure|"
            r"rewrite|r[ée][ée]criture|investment|investissement|co[uû]teu(?:x|se)|"
            r"architecture|release\s+majeure|major\s+release)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "consensus_risk",
        1,
        re.compile(
            r"\b(?:consensus|experts?\s+(?:agree|converge)|tout\s+le\s+monde\s+est\s+d['’]accord|"
            r"influenceurs?|groupthink|pens[ée]e\s+de\s+groupe)\b",
            re.IGNORECASE,
        ),
    ),
)


def evaluate_trigger(
    request: str,
    context: TriggerContext | None = None,
) -> TriggerDecision:
    """Decide whether the outsider agent should be suggested.

    The function classifies only. It never loads a model or executes the agent.
    """
    context = context or TriggerContext()
    text = request.strip()
    signals: list[str] = []
    score = 0

    if _EXPLICIT.search(text):
        signals.append("explicit_request")
        score += 5
    for name, weight, pattern in _SIGNAL_RULES:
        if pattern.search(text):
            signals.append(name)
            score += weight

    contextual = (
        ("context_material_consequence", context.material_consequence, 2),
        ("context_blue_red_stalled", context.blue_red_stalled, 3),
        ("context_inherited_frame", context.inherited_frame, 2),
    )
    for name, enabled, weight in contextual:
        if enabled:
            signals.append(name)
            score += weight

    non_agent_reference = bool(_NON_AGENT_REFERENCE.search(text))
    if non_agent_reference:
        signals.append("non_agent_reference")
        score = max(0, score - 5)

    routine = context.routine_scope or bool(_ROUTINE.search(text))
    if routine:
        signals.append("routine_scope")
        score = max(0, score - 5)

    invoke = (
        bool(text or signals)
        and score >= _THRESHOLD
        and not routine
        and not non_agent_reference
    )
    if non_agent_reference:
        reason = "Monte Cristo is referenced as a subject, not requested as an agent."
    elif routine:
        reason = "Routine scope belongs to a specialist, not Monte Cristo."
    elif invoke:
        reason = "Material frame-level challenge warrants an independent outsider pass."
    else:
        reason = "Insufficient frame-level or material signals; keep the normal workflow."
    return TriggerDecision(invoke, score, _THRESHOLD, tuple(signals), reason)


def should_invoke(request: str, context: TriggerContext | None = None) -> bool:
    """Convenience predicate for orchestrators."""
    return evaluate_trigger(request, context).invoke
