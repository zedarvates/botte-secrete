#!/usr/bin/env python3
"""Selective local Parcimonia assessment for Claude Code's prompt hook.

Read a bounded UserPromptSubmit event (or a plain prompt) from stdin. Assess it
without a model, network call or tool execution, and emit short advisory context
only for supported work or a detected mixed workflow. Unknown and trivial
prompts emit nothing. Any failure leaves the user's prompt unblocked.

This is the existing Claude Code hook, not a Codex/Work-cloud lifecycle hook.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BOTTE_ROOT = Path(__file__).resolve().parents[2]
# The absolute script entry must prefer its own installation, even when the
# caller's PYTHONPATH already lists it after a different checkout.
sys.path.insert(0, str(BOTTE_ROOT))

MAX_INPUT_BYTES = 65_536
MAX_TASK_BYTES = 16_384  # Keep startup independent of the optional assessor.
MAX_CONTEXT_BYTES = 1_024  # Includes main()'s final newline.
_SKILL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_INTENT_NAME = re.compile(r"[a-z][a-z_]{0,63}\Z")
_GUIDANCE = {
    "statistics": "Use an available deterministic statistics tool on supplied values; retain methods, units and missing-value handling.",
    "file_duplicates": "Inspect an explicit local directory through an available read-only exact-file tool; retain byte-comparison evidence, hard-link distinctions and partial scans.",
    "local_links": "Check supplied Markdown and repository paths through an available local-link tool; an incomplete inventory cannot prove a target missing.",
    "github_research": "If available, use plan_github_research, a connected GitHub reader, then summarize_github_evidence for bulky supplied results; retain revisions and partial-read limits.",
    "software_testing": "Use an available test adapter only after checking its prerequisites; retain the target version, command, exit code and observed failures.",
    "game_playtest": "Check the game build, available capture/input/assertion adapters and stop condition; a proposal does not qualify real-time control.",
    "code_work": "Use the scoped code workflow and smallest relevant checks; retain the tested revision and actual results.",
    "content_transform": "Use a suitable available deterministic transformation; preserve facts, negations, conditions and uncertainty.",
    "read_analysis": "Read the scoped sources through available readers; retain provenance and distinguish observations from inference.",
}
_BOUNDARY = "Check current tool schemas and prerequisites. This hint does not establish availability or authorization."


def _read_input() -> tuple[str, Path]:
    cwd = Path.cwd()
    raw = sys.stdin.read(MAX_INPUT_BYTES + 1) if not sys.stdin.isatty() else ""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        return "", cwd
    raw = raw.strip()
    if not raw:
        return "", cwd
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Malformed structured events must not be reinterpreted as instructions.
        return ("", cwd) if raw.startswith(("{", "[")) else (raw, cwd)
    if isinstance(data, str):
        return data, cwd
    if not isinstance(data, dict):
        return "", cwd
    prompt, directory = data.get("prompt", ""), data.get("cwd")
    if not isinstance(prompt, str):
        return "", cwd
    if directory is not None:
        if not isinstance(directory, str) or len(directory.encode("utf-8")) > 4_096:
            return "", cwd
        cwd = Path(directory or ".")
    return prompt, cwd


def _suggested_skills(prompt: str, project: Path) -> list[str]:
    try:
        from skills.skill_finder import find
        roots = [BOTTE_ROOT / "skills"]
        for extra in (project / ".claude" / "skills", project / "skills"):
            if extra.exists():
                roots.append(extra)
        result = find(prompt, roots=roots, top_k=3)
        names = []
        for match in result["matches"]:
            name = match.get("name") if isinstance(match, dict) else None
            if isinstance(name, str) and _SKILL_NAME.fullmatch(name) and name not in names:
                names.append(name)
            if len(names) == 3:
                break
        return names
    except Exception:
        return []


def build_context(prompt: str, project: Path) -> str:
    """Return bounded advisory context, or no context when it is not useful."""
    try:
        if (not isinstance(prompt, str) or not prompt.strip()
                or len(prompt.encode("utf-8")) > MAX_TASK_BYTES):
            return ""
        from skills.preflight.assessment import assess_task
        assessment = assess_task(prompt)
        if assessment.get("status") != "proposed":
            if assessment.get("detected_intents"):
                return "[botte preflight] Parcimonia abstained on a mixed workflow. The host must interpret or split the request before selecting tools; no execution or authorization is inferred."
            return ""
        intent = assessment.get("intent")
        if not isinstance(intent, str) or not _INTENT_NAME.fullmatch(intent):
            return ""
        lines = [f"[botte preflight] Parcimonia: {intent} (local lexical proposal; no tool execution).",
                 _GUIDANCE.get(intent, "Use the supported workflow only after checking its tools and evidence requirements."),
                 _BOUNDARY]
        # The GitHub workflow already names its conditional helpers. Avoid a
        # second catalog scan whose weak skill matches add no useful evidence.
        skills = [] if intent == "github_research" else _suggested_skills(prompt, Path(project))
        if skills:
            suggestion = "Skill hints (local metadata, not verified capabilities): " + ", ".join(skills)
            if len(("\n".join(lines + [suggestion]) + "\n").encode("utf-8")) <= MAX_CONTEXT_BYTES:
                lines.append(suggestion)
        context = "\n".join(lines)
        return context if len((context + "\n").encode("utf-8")) <= MAX_CONTEXT_BYTES else ""
    except Exception:
        return ""


def main() -> int:
    try:
        prompt, cwd = _read_input()
        context = build_context(prompt, cwd) if prompt else ""
        if context:
            sys.stdout.write(context + "\n")
    except Exception:
        # A failed hook must never block the user's prompt.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
