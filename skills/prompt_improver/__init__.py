"""prompt_improver — rewrite rough prompts into professional structured prompts.

    from skills.prompt_improver import improve
    improve("make my code faster")                 # local-LLM, markdown
    improve("make my code faster", as_json=True)    # strict JSON prompt object

Runs on a local model (0 cloud tokens); falls back to a deterministic scaffold
when no local backend is available.
"""

from skills.prompt_improver.improver import (
    improve, scaffold, StructuredPrompt, PROMPT_SCHEMA_KEYS,
)

__all__ = ["improve", "scaffold", "StructuredPrompt", "PROMPT_SCHEMA_KEYS"]
