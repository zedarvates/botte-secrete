"""Build validated shared-memory checkpoint proposals from an ExecutionHarness.

This module never calls the Memory Hub service and never writes memory. It only
constructs an input that satisfies the existing versioned shared-memory
contract, preserving the separation between observed execution state and a
future explicit memory write.
"""

from __future__ import annotations

import json
from typing import Any

from skills.execution_harness.contract import ExecutionHarness
from skills.memory_hub.shared_contract import SCHEMAS, validate


def build_checkpoint_proposal(
    harness: ExecutionHarness,
    *,
    project_id: str,
    key: str,
    request_id: str,
    run_id: str,
    observed_at: float,
    source_id: str = "execution-harness",
    source_excerpt: str = "ExecutionHarness handoff checkpoint proposal",
) -> dict[str, Any]:
    """Return a validated but deliberately unexecuted Memory Hub proposal.

    The proposal contains only verified evidence references by default. It does
    not inject agent identity, trust class, review status, or execution
    authority because the shared-memory contract owns those decisions.
    """
    handoff = harness.handoff or harness.build_handoff(completed=(), remaining=())
    verified_refs = [item.ref for item in harness.evidence if item.verified][:20]

    text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) > 16_000:
        raise ValueError("harness handoff exceeds shared-memory checkpoint text limit")

    arguments = {
        "project_id": project_id,
        "key": key,
        "request_id": request_id,
        "record": {
            "text": text,
            "kind": "checkpoint",
            "source": {
                "type": "generated",
                "id": source_id,
                "run_id": run_id,
                "observed_at": observed_at,
                "excerpt": source_excerpt,
            },
            "visibility": "project",
            "evidence_refs": verified_refs,
            "tags": ["execution-harness", "handoff", "proposal"],
        },
    }
    validate(SCHEMAS["checkpoint"], arguments)
    return {
        "schema_version": "botte.execution-harness-memory-proposal/v1",
        "operation": "checkpoint",
        "arguments": arguments,
        "executed": False,
        "memory_write_performed": False,
        "activation_allowed": False,
        "review_required": True,
    }


__all__ = ["build_checkpoint_proposal"]
