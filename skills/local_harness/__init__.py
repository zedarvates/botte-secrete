"""local_harness — wrap a local-model call in deterministic guardrails so small
models can't hallucinate freely. See docs/plans/2026-06-26_local-model-harness-spec.md.

verifier (layer 3) + the HarnessSpec executor (all five layers: gate → constrain →
ground → verify → abstain/escalate → learn).
"""

from skills.local_harness.verifier import (
    verify, schema_ok, evidence_in_context, citations_exist, code_parses,
    CheckResult, VerifyResult,
)
from skills.local_harness.spec import HarnessSpec
from skills.local_harness.executor import run_harness, HarnessResult

__all__ = [
    "verify", "schema_ok", "evidence_in_context", "citations_exist",
    "code_parses", "CheckResult", "VerifyResult",
    "HarnessSpec", "run_harness", "HarnessResult",
]
