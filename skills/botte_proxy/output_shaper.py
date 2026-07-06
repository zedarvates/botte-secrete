"""Output Shaper — reduce tokens the model writes back.

Two strategies:
1. **Verbosity steering** — inject a "be concise" instruction into the system prompt
   so the model outputs fewer tokens in the first place.
2. **Content trimming** — post-process the response to strip verbose preambles,
   restated code, thinking blocks, and other waste.

Counterfactual estimation: we hold out ~10% of requests from shaping to measure
real savings vs. unshaped baselines.
"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Optional

# ── Verbosity steering prompt ──────────────────────────────────

VERBOSITY_STEER = (
    "\n\n[Output instructions]\n"
    "Be terse and direct. Don't restate what the user just showed you. "
    "Skip 'Sure!', 'Great question!', 'I'd be happy to help', and similar preambles. "
    "Don't recite code back unless asked. Answer in the fewest tokens that carry the answer."
)

# ── Patterns to trim from model responses ─────────────────────

# Verbose preamble patterns (case-insensitive)
# Each pattern must match the ENTIRE preamble up to and including the transition
VERBOSE_PREAMBLES = [
    # Leading AI preamble patterns (matched as phrase starts)
    r"^(Sure|Certainly|Of course|Absolutely|Great|Perfect|Excellent|Awesome)[!,.]*\s+",
    r"^I'[dvm]\s+(be\s+)?(happy|glad|pleased)\s+to\s+",
    r"^Let\s+me\s+(explain|provide|show|give|help|walk|start|begin|demonstrate)\s+",
    r"^Here['s]?\s+is\s+(the|my|a|an)\s+",
    r"^(Great|Excellent|Perfect)\s+(question|point|catch|idea)[!,.]*\s*",
    r"^That['s]?\s+(is\s+)?a\s+(great|good|excellent)\s+(question|point)[!,.]*\s*",
    r"^No\s+(problem|worries|issues)[!,.]*\s*",
]


def _trim_preamble(content: str) -> str:
    """Strip verbose preamble from the first line/sentence."""
    for pattern in VERBOSE_PREAMBLES:
        # Try matching at the start — if matched, strip to the first period
        # or newline that follows
        match = re.match(pattern, content, re.IGNORECASE)
        if match:
            # Find end of first sentence
            rest = content[match.end():]
            # Look for the end of the first sentence (period + space or newline)
            sentence_end = re.search(r'[.!?:]\s+|\.$|\n', rest)
            if sentence_end:
                end_pos = match.end() + sentence_end.end()
                result = content[end_pos:].lstrip()
                # Only use if we save meaningful space
                if len(result) < len(content) * 0.85:
                    return result
            else:
                # No sentence end found — strip the matched part only
                result = content[match.end():].lstrip()
                if len(result) < len(content) * 0.85:
                    return result
    return content

# Markers for sections to compress/remove
THINKING_PATTERN = re.compile(
    r'<thinking>.*?</thinking>',
    re.DOTALL,
)

RESTATED_CODE_PATTERN = re.compile(
    r'(Here\'s|Here is|Below is)\s+(the\s+)?(updated|modified|corrected|fixed|complete|full)\s+(code|implementation|version):',
    re.IGNORECASE,
)

FOOTER_PATTERNS = [
    r"Let me know if you",
    r"Feel free to ask",
    r"Please let me know",
    r"Don't hesitate to",
    r"I hope this",
    r"This should",
]

# Common closing signatures
CLOSING_SIGNATURES = [
    r"Best( regards)?[,:]?\s*$",
    r"Thanks[,:]?\s*$",
    r"Cheers[,:]?\s*$",
    r"--\s*$",
]

# ── Config ─────────────────────────────────────────────────────

# Holdout rate: fraction of requests to leave unshaped for measurement
HOLDOUT_RATE = float(os.environ.get("BOTTE_OUTPUT_HOLDOUT", "0.0"))


def should_shape() -> bool:
    """Decide whether to apply output shaping (random holdout)."""
    if HOLDOUT_RATE <= 0:
        return True
    return random.random() > HOLDOUT_RATE


def add_verbosity_steer(messages: list[dict]) -> list[dict]:
    """Add verbosity steering instruction to the system message.

    Appends a short "be terse" instruction to the last system message,
    or creates one if no system message exists.
    """
    result = list(messages)
    for i, msg in enumerate(result):
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            result[i] = dict(msg)
            result[i]["content"] = msg["content"] + VERBOSITY_STEER
            return result

    # No system message — add one
    result.insert(0, {"role": "system", "content": VERBOSITY_STEER.strip()})
    return result


def trim_response_content(content: str) -> str:
    """Trim verbosity from a model response.

    Removes or compresses:
    - Verbose preambles
    - thinking blocks
    - Restated code signals
    - Footer pleasantries
    """
    original = content

    # 1. Strip thinking blocks
    content = THINKING_PATTERN.sub("", content)

    # 2. Trim verbose preambles
    content = _trim_preamble(content)

    # 3. Shorten restated code markers
    content = RESTATED_CODE_PATTERN.sub("Updated code:", content)

    # 4. Remove trailing footers
    lines = content.split("\n")
    while lines:
        stripped = lines[-1].strip()
        if not stripped:
            lines.pop()
        elif any(re.search(p, stripped, re.IGNORECASE) for p in FOOTER_PATTERNS):
            lines.pop()
        elif any(re.search(p, stripped) for p in CLOSING_SIGNATURES):
            lines.pop()
        else:
            break

    content = "\n".join(lines)

    # Only use trimmed version if it saves meaningful space (>=10%)
    if len(content) < len(original) * 0.9:
        return content
    return original


def shape_response(
    response_body: dict,
    shaped: bool = True,
) -> tuple[dict, int, int]:
    """Shape (trim) the response content from a chat completion.

    Returns (modified_body, original_tokens, shaped_tokens).
    Only modifies the 'content' field of each choice's message.
    """
    original_text = ""
    shaped_text = ""

    for choice in response_body.get("choices", []):
        msg = choice.get("message", {})
        content = msg.get("content", "")

        if not isinstance(content, str) or not content.strip():
            continue

        original_text += content

        if shaped:
            trimmed = trim_response_content(content)
        else:
            trimmed = content

        shaped_text += trimmed

        if trimmed != content:
            msg["content"] = trimmed

    original_tokens = max(1, len(original_text) // 4)
    shaped_tokens = max(1, len(shaped_text) // 4)

    return response_body, original_tokens, shaped_tokens
