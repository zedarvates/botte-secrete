"""HarnessSpec — a declarative anti-hallucination harness for a local model.

A harness is a *file*, not code: it says which guardrails wrap a local-model call.
See docs/plans/2026-06-26_local-model-harness-spec.md for the full format. This
module loads that YAML/dict into a flat dataclass the executor can run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class HarnessSpec:
    name: str = "harness"
    model: str = "auto"
    # gate
    max_effort: float = 1.0
    allow_task_types: list[str] = field(default_factory=list)
    strict: bool = False  # silently refuse critical tasks, force cloud escalation
    # output (constrain)
    output_format: str = "json_object"        # free_text | json_object | json_schema | enum
    output_schema: Optional[dict] = None
    enum: Optional[list[str]] = None
    max_tokens: int = 512
    # ground
    ground_source: str = "none"               # qdrant://… | files:… | none
    ground_rule: str = ""                     # e.g. answer_from_context_only
    escalate_token: str = "NEEDS_ESCALATION"
    # verify
    verify: list[str] = field(default_factory=list)
    # self-consistency
    samples: int = 1
    agree: int = 1
    # policy
    on_fail: str = "escalate"                 # escalate | abstain | return_best
    escalate_to: str = "STANDARD"
    learn: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "HarnessSpec":
        """Build from the nested YAML structure (gate/output/ground/…)."""
        d = d or {}
        gate = d.get("gate") or {}
        out = d.get("output") or {}
        ground = d.get("ground") or {}
        sc = d.get("self_consistency") or {}
        return cls(
            name=d.get("harness", d.get("name", "harness")),
            model=d.get("model", "auto"),
            max_effort=float(gate.get("max_effort", 1.0)),
            allow_task_types=list(gate.get("allow_task_types", []) or []),
            output_format=out.get("format", "json_object"),
            output_schema=out.get("schema"),
            enum=out.get("enum"),
            max_tokens=int(out.get("max_tokens", 512)),
            ground_source=ground.get("source", "none"),
            ground_rule=ground.get("rule", ""),
            escalate_token=ground.get("escalate_token", "NEEDS_ESCALATION"),
            verify=list(d.get("verify", []) or []),
            samples=int(sc.get("samples", 1)),
            agree=int(sc.get("agree", 1)),
            on_fail=d.get("on_fail", "escalate"),
            escalate_to=d.get("escalate_to", "STANDARD"),
            learn=bool(d.get("learn", False)),
        )

    @classmethod
    def load(cls, path: str | Path) -> "HarnessSpec":
        """Load a harness from a .yaml/.yml/.json file."""
        text = Path(path).read_text(encoding="utf-8")
        p = str(path).lower()
        if p.endswith((".yaml", ".yml")):
            import yaml  # lazy — matches meta_harness.pipeline_dsl
            data = yaml.safe_load(text)
        else:
            import json
            data = json.loads(text)
        return cls.from_dict(data)
