"""local_harness — wrap a local-model call in deterministic guardrails so small
models can't hallucinate freely. See docs/plans/2026-06-26_local-model-harness-spec.md.

Layer 3 (verifier) ships first; the HarnessSpec executor builds on it.
"""

from skills.local_harness.verifier import (
    verify, schema_ok, evidence_in_context, citations_exist, code_parses,
    CheckResult, VerifyResult,
)

__all__ = [
    "verify", "schema_ok", "evidence_in_context", "citations_exist",
    "code_parses", "CheckResult", "VerifyResult",
]
