"""Five short read-only choices mapped to the existing shared-memory contract.

The host supplies the project. Identity/authorization remain in the configured
MCP/HTTP client; this module neither reads credentials nor dispatches proposals.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import time
import uuid

from skills.memory_hub.shared_contract import (
    PROJECT, IDENTIFIER, READ_ONLY, SCHEMAS, encode, obj, string, validate,
)
from .base import ToolRouteResult, ToolSpec

CONTRACT_VERSION = "botte.needle2-memory-pilot/v1"
OPERATIONS = {
    "memory_context": "recall", "memory_observations": "recall",
    "memory_history": "history", "memory_wiki": "wiki", "memory_scribe": "scribe",
}


def memory_tools():
    """A fresh catalog per caller. No project, identity, or write tools exposed."""
    query = obj({"query": {"type": "string", "maxLength": 256}})
    return (
        ToolSpec("memory_context",
                 "Recall reviewed facts, decisions and preferences. Contexte valide, decisions, preferences.", query),
        ToolSpec("memory_observations",
                 "Find unverified agent reports, CI evidence and quarantined observations. Rapports, preuves CI, quarantaine.", query),
        ToolSpec("memory_history",
                 "Read revisions of a memory with a known exact key. Historique des versions d'une cle memoire.",
                 obj({"key": dict(IDENTIFIER)}, ("key",))),
        ToolSpec("memory_wiki",
                 "Show a cited Markdown wiki view. Afficher la vue wiki Markdown du projet.", query),
        ToolSpec("memory_scribe",
                 "Find memories similar to supplied text, advisory only. Scribe: comparer un texte aux souvenirs proches.",
                 obj({"text": string(256)}, ("text",))),
    )


def catalog_sha256():
    return hashlib.sha256(encode([t.as_dict() for t in memory_tools()])).hexdigest()


def memory_call(route: ToolRouteResult, project_id: str):
    """Build one validated MCP call for review, without making that call."""
    validate(PROJECT, project_id, "project_id")
    if route.abstained:
        return None
    specs = {tool.name: tool for tool in memory_tools()}
    if route.tool_name not in specs:
        raise ValueError("tool is outside the memory pilot")
    validate(specs[route.tool_name].parameters, route.arguments)
    operation = OPERATIONS[route.tool_name]
    if operation not in READ_ONLY:
        raise ValueError("write operations are outside the pilot")
    args = {"project_id": project_id, **dict(route.arguments)}
    if route.tool_name in {"memory_context", "memory_observations"}:
        args.update(area="context" if route.tool_name == "memory_context" else "observations",
                    limit=5, max_bytes=8192)
    elif route.tool_name == "memory_wiki":
        args.update(limit=5, max_bytes=8192)
    elif route.tool_name == "memory_scribe":
        text = args.pop("text")
        # Ephemeral query record, explicitly generated. Scribe reads it without
        # capturing/promoting it or fabricating evidence of a successful action.
        args["record"] = {
            "text": text, "kind": "observation",
            "source": {"type": "generated", "id": "needle2-advisory",
                       "run_id": "query-" + uuid.uuid4().hex,
                       "observed_at": time.time(), "excerpt": text},
        }
    validate(SCHEMAS[operation], args)
    return {"name": "memory_" + operation, "arguments": args}


def propose(query, router, project_id):
    validate(PROJECT, project_id, "project_id")
    route = router.route(query, memory_tools())
    return {"schema_version": CONTRACT_VERSION, "mode": "advisory",
            "catalog_sha256": catalog_sha256(), "route": asdict(route),
            "memory_call": memory_call(route, project_id),
            "executed": False, "activation_allowed": False,
            "effects": {"memory_writes": 0, "tool_calls_executed": 0},
            "limitations": ["routing_accuracy_unverified_on_user_tasks",
                            "proposal_requires_host_validation_and_authorization"]}
