"""Prompt improver — turn a rough prompt into a professional, structured one.

Rewriting a prompt is text transformation, not hard reasoning — so it runs on a
LOCAL model for 0 cloud tokens (via skills.llm_backends). Output as structured
markdown or as a strict JSON prompt object.

The structure follows well-established prompt-engineering practice:

    role          who the model should act as
    context       background it needs
    task          the single, explicit objective
    instructions  ordered steps
    constraints   hard rules / what NOT to do
    output_format how the answer must be shaped
    examples      optional few-shot input/output pairs
    success_criteria  machine-checkable "done" conditions

Pure stdlib + the local client. No cloud calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


# Canonical JSON prompt schema (the "prompt object").
PROMPT_SCHEMA_KEYS = (
    "role", "context", "task", "instructions", "constraints",
    "output_format", "examples", "success_criteria",
)


@dataclass
class StructuredPrompt:
    role: str = ""
    context: str = ""
    task: str = ""
    instructions: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    output_format: str = ""
    examples: list = field(default_factory=list)
    success_criteria: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in PROMPT_SCHEMA_KEYS}

    def to_markdown(self) -> str:
        L = []
        if self.role:
            L.append(f"# Role\n{self.role}")
        if self.context:
            L.append(f"# Context\n{self.context}")
        if self.task:
            L.append(f"# Task\n{self.task}")
        if self.instructions:
            L.append("# Instructions\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(self.instructions)))
        if self.constraints:
            L.append("# Constraints\n" + "\n".join(f"- {c}" for c in self.constraints))
        if self.output_format:
            L.append(f"# Output format\n{self.output_format}")
        if self.examples:
            ex = "\n".join(f"- input: {e.get('input','')}\n  output: {e.get('output','')}"
                           for e in self.examples if isinstance(e, dict))
            if ex:
                L.append("# Examples\n" + ex)
        if self.success_criteria:
            L.append("# Success criteria\n" + "\n".join(f"- {c}" for c in self.success_criteria))
        return "\n\n".join(L)


# ── deterministic scaffold (0 tokens, used as fallback / seed) ────────────────

def scaffold(raw: str) -> StructuredPrompt:
    """Wrap a raw prompt into the schema skeleton without any model call."""
    raw = raw.strip()
    return StructuredPrompt(
        role="You are an expert assistant for this task.",
        task=raw,
        output_format="Respond concisely and directly; use markdown when helpful.",
        success_criteria=["The answer fully addresses the task.",
                          "No assumptions are left unstated."],
    )


# ── local-LLM rewrite (0 cloud tokens) ────────────────────────────────────────

_META = (
    "You are a senior prompt engineer. Rewrite the user's rough prompt into a "
    "professional, unambiguous prompt. Add a clear role, only the context that "
    "matters, one explicit task, ordered instructions, hard constraints, an "
    "explicit output format, and machine-checkable success criteria. Do NOT "
    "answer the prompt itself — only improve it. Keep it tight; invent no facts."
)

_META_JSON = _META + (
    "\nReturn STRICT JSON only (no prose, no code fences) with exactly these keys: "
    + ", ".join(PROMPT_SCHEMA_KEYS) +
    ". 'instructions', 'constraints', 'success_criteria' are arrays of strings; "
    "'examples' is an array of {input, output} objects (may be empty)."
)


def _local_backend_available() -> bool:
    try:
        from skills.llm_backends import registry
        return registry.best_chat_backend() is not None
    except ImportError:
        return False


def _local_chat(prompt: str, system: str, max_tokens: int) -> Optional[str]:
    try:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
    except ImportError:
        return None
    try:
        return LocalLLMClient().chat(prompt, system=system, max_tokens=max_tokens,
                                     temperature=0.3).text
    except LocalLLMError:
        return None


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response (handles fences)."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _coerce(d: dict) -> StructuredPrompt:
    def _list(v):
        if isinstance(v, list):
            return [str(x) if not isinstance(x, dict) else x for x in v]
        return [str(v)] if v else []
    return StructuredPrompt(
        role=str(d.get("role", "")), context=str(d.get("context", "")),
        task=str(d.get("task", "")), instructions=_list(d.get("instructions")),
        constraints=_list(d.get("constraints")), output_format=str(d.get("output_format", "")),
        examples=[e for e in d.get("examples", []) if isinstance(e, dict)],
        success_criteria=_list(d.get("success_criteria")),
    )


def improve(raw: str, *, as_json: bool = False, use_local: bool = True,
            max_tokens: int = 700) -> dict:
    """Improve a raw prompt. Returns dict with structured prompt + metadata.

    With a local backend: the model rewrites it (0 cloud tokens). Without one (or
    use_local=False): returns the deterministic scaffold so the call never fails.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"error": "empty prompt"}

    tier = "scaffold"
    sp = scaffold(raw)

    if use_local and _local_backend_available():
        system = _META_JSON if as_json else _META
        out = _local_chat(f"Rough prompt:\n{raw}", system, max_tokens)
        if out:
            if as_json:
                parsed = _extract_json(out)
                if parsed:
                    sp = _coerce(parsed)
                    tier = "local-llm-json"
                else:
                    sp.task = raw  # keep scaffold; note parse miss
                    tier = "scaffold (json parse failed)"
            else:
                # free-text improvement: keep the model's prose as the task body
                sp = scaffold(raw)
                sp.task = out.strip()
                tier = "local-llm-text"

    result = {
        "tier": tier, "cloud_tokens": 0,
        "structured": sp.to_dict(),
        "markdown": sp.to_markdown(),
    }
    if as_json:
        result["json_prompt"] = json.dumps(sp.to_dict(), ensure_ascii=False, indent=2)
    return result
