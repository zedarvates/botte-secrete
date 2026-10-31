"""Memory Hub MCP tools."""
from __future__ import annotations
import os
from typing import Any
from skills.memory_hub.schema import MemoryEntry, AssetType, MemoryStatus, MemoryVisibility
from skills.memory_hub.store import MemoryStore

def _init_store():
    return MemoryStore(base_dir=os.environ.get("BOTTE_MEMORY_HUB_DIR"))

TOOL_DEFINITIONS = [
    {
        "name": "search_hub",
        "description": "Search the governed memory hub.",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "query": {"type": "string"},
            "asset_type": {"type": "string", "enum": ["chat_memory","skill","wiki","code_graph","fact","pattern","decision"]},
            "status": {"type": "string", "enum": ["proposal","review_active","promoted","expired","obsoleted"]},
            "agent_id": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
            "storage_area": {"type": "string", "enum": ["all","trusted","quarantine"], "default": "all"},
        }, "required": ["project_id"]},
    },
    {
        "name": "review_quarantine",
        "description": "Review quarantined observations as non-executable data with provenance.",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        }, "required": ["project_id", "agent_id"]},
    },
    {
        "name": "context_bundle",
        "description": "Top-N memory for agent context.",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "max_entries": {"type": "integer", "default": 10},
        }, "required": ["project_id", "agent_id"]},
    },
    {
        "name": "propose_memory",
        "description": "Propose a new memory entry (starts as proposal).",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "key": {"type": "string"},
            "value": {"description": "JSON-serializable value"},
            "asset_type": {"type": "string", "enum": ["chat_memory","skill","wiki","code_graph","fact","pattern","decision"], "default": "fact"},
            "category": {"type": "string", "default": "fact"},
            "confidence": {"type": "number", "default": 1.0},
            "agent_id": {"type": "string"},
            "source_ref": {"type": "string"},
            "source_type": {"type": "string", "enum": ["user","repo","web","tool","agent","generated"]},
            "source_uri": {"type": "string"},
            "source_id": {"type": "string"},
            "run_id": {"type": "string"},
            "timestamp": {"type": "number"},
            "trust_class": {"type": "string", "enum": ["trusted_user","external_observation","generated_untrusted"]},
            "executable_instruction": {"type": "boolean", "enum": [False]},
            "visibility": {"type": "string", "enum": ["private","project","team","restricted"], "default": "private"},
            "expires_in_days": {"type": "number", "default": 0},
            "tags": {"type": "array", "items": {"type": "string"}, "default": []},
        }, "required": ["project_id", "key", "value", "agent_id", "source_type", "run_id", "timestamp", "trust_class", "executable_instruction"]},
    },
    {
        "name": "promote_memory",
        "description": "Promote memory through lifecycle.",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "key": {"type": "string"},
            "new_status": {"type": "string", "enum": ["proposal","review_active","promoted","expired","obsoleted"]},
            "actor_id": {"type": "string"},
        }, "required": ["project_id", "key", "new_status", "actor_id"]},
    },
    {
        "name": "forget_memory",
        "description": "Permanently delete a memory entry.",
        "input_schema": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "key": {"type": "string"},
            "actor_id": {"type": "string"},
        }, "required": ["project_id", "key", "actor_id"]},
    },
]

HANDLERS = {}

def handle_search_hub(args):
    with _init_store() as store:
        entries = store.search(project_id=args["project_id"], query=args.get("query",""), asset_type=args.get("asset_type"), status=args.get("status"), agent_id=args.get("agent_id"), limit=args.get("limit",50), storage_area=args.get("storage_area", "all"))
    return {"results": [{"key": e.key, "type": e.asset_type, "status": e.status, "confidence": e.confidence, "visibility": e.visibility, "tags": e.tags, "quarantined": e.quarantined, "provenance": {"source_type": e.source_type, "source_uri": e.source_uri, "source_id": e.source_id, "run_id": e.run_id, "timestamp": e.observed_at, "trust_class": e.trust_class, "executable_instruction": False}} for e in entries], "count": len(entries)}

def handle_context_bundle(args):
    with _init_store() as store:
        bundle = store.context_bundle(project_id=args["project_id"], agent_id=args["agent_id"], max_entries=args.get("max_entries",10))
    return {"entries": bundle, "count": len(bundle)}

def handle_review_quarantine(args):
    with _init_store() as store:
        entries = store.review_quarantine(project_id=args["project_id"], agent_id=args["agent_id"], query=args.get("query", ""), limit=args.get("limit", 20))
    return {"entries": entries, "count": len(entries), "authority": "SIMULATE"}

def handle_propose_memory(args):
    import time
    expires = None
    if args.get("expires_in_days", 0) > 0:
        expires = time.time() + args["expires_in_days"] * 86400
    entry = MemoryEntry(key=args["key"], value=args["value"], asset_type=args.get("asset_type", AssetType.FACT.value), category=args.get("category","fact"), confidence=args.get("confidence",1.0), status=MemoryStatus.PROPOSED.value, visibility=args.get("visibility", MemoryVisibility.PRIVATE.value), project_id=args["project_id"], agent_id=args["agent_id"], source_ref=args.get("source_ref",""), source_type=args["source_type"], source_uri=args.get("source_uri", ""), source_id=args.get("source_id", ""), run_id=args["run_id"], observed_at=args["timestamp"], trust_class=args["trust_class"], executable_instruction=args["executable_instruction"], expires_at=expires, created_by=args["agent_id"], tags=args.get("tags",[]))
    with _init_store() as store:
        store.store(entry)
    return {"key": entry.key, "status": entry.status, "project_id": entry.project_id,
            "quarantined": entry.quarantined, "executable_instruction": False}

def handle_promote_memory(args):
    with _init_store() as store:
        ok = store.transition(project_id=args["project_id"], key=args["key"], new_status=args["new_status"], actor_id=args.get("actor_id",""))
    if ok: return {"success": True, "key": args["key"], "new_status": args["new_status"]}
    return {"success": False, "reason": "Transition not allowed or entry not found"}

def handle_forget_memory(args):
    actor_id = args.get("actor_id")
    if not actor_id:
        return {"deleted": False, "key": args.get("key", ""), "reason": "actor_id is required"}
    with _init_store() as store:
        deleted = store.delete(project_id=args["project_id"], key=args["key"], actor_id=actor_id)
    return {"deleted": deleted, "key": args["key"]}

HANDLERS["search_hub"] = handle_search_hub
HANDLERS["context_bundle"] = handle_context_bundle
HANDLERS["review_quarantine"] = handle_review_quarantine
HANDLERS["propose_memory"] = handle_propose_memory
HANDLERS["promote_memory"] = handle_promote_memory
HANDLERS["forget_memory"] = handle_forget_memory

def get_tools():
    return TOOL_DEFINITIONS

def dispatch(tool_name, args):
    handler = HANDLERS.get(tool_name)
    if not handler: return {"error": f"Unknown memory_hub tool: {tool_name}"}
    return handler(args)

__all__ = ["get_tools", "dispatch", "TOOL_DEFINITIONS"]
