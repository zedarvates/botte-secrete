"""Cost-ordered decision controller for a single loop iteration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from skills.loop_optimizer.guards import stop_decision
from skills.loop_optimizer.ledger import LoopLedger
from skills.loop_optimizer.models import LoopAction, LoopDecision, LoopOutcome, LoopRequest, LoopState
from skills.response_cache import ResponseCache
from skills.events.events import log_event


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def lexical_tools(query: str, catalog: dict[str, str], allowed: Iterable[str]) -> list[str]:
    """Return allowed tools ranked by zero-token lexical relevance."""
    words = _tokens(query)
    allowed_set = set(allowed)
    ranked = []
    for name, description in catalog.items():
        if allowed_set and name not in allowed_set:
            continue
        name_hits = len(words & _tokens(name.replace("_", " ")))
        description_hits = len(words & _tokens(description))
        score = 3 * name_hits + description_hits
        if score:
            ranked.append((-score, name))
    return [name for _, name in sorted(ranked)]


@dataclass(frozen=True, slots=True)
class AgentSelection:
    run: tuple[str, ...]
    skipped: tuple[str, ...]
    reason: str


class LoopController:
    """Decide without executing tools, LLMs, commands or network calls."""

    def __init__(self, *, cache: ResponseCache | None = None,
                 ledger: LoopLedger | None = None, project_root: str | Path = "."):
        self.cache = cache or ResponseCache()
        self.ledger = ledger or LoopLedger()
        self.project_root = project_root

    def _event(self, kind: str, **fields: Any) -> None:
        log_event(kind, self.project_root, **fields)

    @staticmethod
    def _cache_material(request: LoopRequest, state: LoopState,
                        catalog: dict[str, str], context: str) -> str:
        return json.dumps({
            "goal": request.goal,
            "allowed_tools": request.allowed_tools,
            "criticality": request.criticality,
            "state": state.to_dict(),
            "catalog": catalog,
            "context": context,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def decide(self, request: LoopRequest, state: LoopState, *,
               tool_catalog: dict[str, str] | None = None,
               context: str = "", consecutive_stalled: int = 0,
               repeated_failure: bool = False,
               fingerprints_unchanged: bool = False) -> LoopDecision:
        if request.loop_id != state.loop_id:
            raise ValueError("request and state loop_id must match")
        self._event("loop_start", loop_id=request.loop_id, iteration=state.iteration,
                    tokens=state.total_tokens, criticality=request.criticality)
        guarded = stop_decision(request, state, consecutive_stalled=consecutive_stalled,
                                repeated_failure=repeated_failure,
                                fingerprints_unchanged=fingerprints_unchanged)
        if guarded is not None:
            self._event("loop_stop", loop_id=request.loop_id, iteration=state.iteration,
                        reason=guarded.stop_reason.value if guarded.stop_reason else "guard")
            return guarded

        catalog = tool_catalog or {}
        material = self._cache_material(request, state, catalog, context)
        hit = self.cache.get(material, model="loop-controller", context="decision",
                             use_semantic=False)
        if hit is not None:
            try:
                stored = json.loads(hit.response)
                decision = LoopDecision(stored["action"], stored["reason"],
                                    decided_by="exact_cache", tool=stored.get("tool", ""),
                                    confidence=float(stored.get("confidence", 1.0)),
                                    stop_reason=stored.get("stop_reason"))
                self._event("loop_decision", loop_id=request.loop_id, iteration=state.iteration,
                            action=decision.action.value, decided_by=decision.decided_by)
                return decision
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass

        candidates = lexical_tools(request.goal + "\n" + context, catalog, request.allowed_tools)
        if len(candidates) == 1:
            decision = LoopDecision(LoopAction.CHANGE_TOOL,
                                    "one lexically relevant allowed tool",
                                    decided_by="lexical", tool=candidates[0])
        elif candidates:
            decision = LoopDecision(LoopAction.ASK_LOCAL,
                                    f"{len(candidates)} allowed tools remain ambiguous",
                                    decided_by="lexical")
        else:
            decision = LoopDecision(LoopAction.RETRY_LOCAL,
                                    "no allowed lexical tool match; request local reasoning",
                                    decided_by="deterministic")
        self.cache.set(material, json.dumps(decision.to_dict(), ensure_ascii=False,
                                            separators=(",", ":")),
                       model="loop-controller", context="decision", tokens_used=0)
        self._event("loop_decision", loop_id=request.loop_id, iteration=state.iteration,
                    action=decision.action.value, decided_by=decision.decided_by)
        return decision

    def select_agents(self, agents: Iterable[str], *, required: Iterable[str] = (),
                      domain_matches: Iterable[str] = (), cache_hit: bool = False,
                      criticality: float = 0.0) -> AgentSelection:
        """Apply deterministic selection before consulting the optional NN hint."""
        all_agents = tuple(agents)
        required_set, domain_set = set(required), set(domain_matches)
        run = tuple(agent for agent in all_agents if agent in required_set or agent in domain_set)
        if run:
            skipped = tuple(agent for agent in all_agents if agent not in run)
            return AgentSelection(run, skipped, "required/domain rules")
        if cache_hit:
            return AgentSelection((), all_agents, "exact cache hit")
        if criticality >= 0.8:
            return AgentSelection(all_agents, (), "critical loop forbids learned skip")
        try:
            from skills.auto_router.nn_belt2 import skip_agent_hint
            hint = skip_agent_hint(fingerprint_match=0.0, agent_type="analyze",
                                   cache_history=1.0 if cache_hit else 0.0,
                                   criticality=criticality)
        except Exception:
            hint = None
        if hint and hint[0] == "skip":
            return AgentSelection((), all_agents, f"belt skip confidence {hint[1]:.2f}")
        return AgentSelection(all_agents, (), "belt abstained or execute")

    def explain(self, request: LoopRequest, state: LoopState, **kwargs: Any) -> dict[str, Any]:
        decision = self.decide(request, state, **kwargs)
        cloud_hint = None
        try:
            from skills.auto_router.nn_belt2 import cloud_escalation_hint
            cloud_hint = cloud_escalation_hint(criticality=request.criticality)
        except Exception:
            pass
        return {
            "loop_id": request.loop_id,
            "decision": decision.to_dict(),
            "cost_order": ["guards", "exact_cache", "lexical", "belt", "local", "cloud"],
            "cloud_hint": cloud_hint,
            "state": state.to_dict(),
        }

    def record(self, outcome: LoopOutcome) -> dict[str, Any]:
        record = self.ledger.append(outcome)
        self._event("loop_saving", loop_id=outcome.loop_id, iteration=outcome.iteration,
                    cache_hit=outcome.cache_hit, tokens_used=outcome.total_tokens,
                    cloud_tokens=outcome.cloud_tokens)
        if outcome.success:
            self._event("loop_stop", loop_id=outcome.loop_id, iteration=outcome.iteration,
                        reason="solved")
        return record
