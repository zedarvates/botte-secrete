"""Memory Hub MCP tools."""
from __future__ import annotations
from typing import Any
from skills.memory_hub.schema import MemoryEntry, AssetType, MemoryStatus, MemoryVisibility
from skills.memory_hub.store import MemoryStore

def _init_store():
    return MemoryStore()

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
        }, "required": ["project_id"]},
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
            "visibility": {"type": "string", "enum": ["private","project","team","restricted"], "default": "private"},
            "expires_in_days": {"type": "number", "default": 0},
            "tags": {"type": "array", "items": {"type": "string"}, "default": []},
        }, "required": ["project_id", "key", "value", "agent_id"]},
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
    store = _init_store()
    entries = store.search(project_id=args["project_id"], query=args.get("query",""), asset_type=args.get("asset_type"), status=args.get("status"), agent_id=args.get("agent_id"), limit=args.get("limit",50))
    return {"results": [{"key": e.key, "type": e.asset_type, "status": e.status, "confidence": e.confidence, "visibility": e.visibility, "tags": e.tags} for e in entries], "count": len(entries)}

def handle_context_bundle(args):
    store = _init_store()
    bundle = store.context_bundle(project_id=args["project_id"], agent_id=args["agent_id"], max_entries=args.get("max_entries",10))
    return {"entries": bundle, "count": len(bundle)}

def handle_propose_memory(args):
    import time
    expires = None
    if args.get("expires_in_days", 0) > 0:
        expires = time.time() + args["expires_in_days"] * 86400
    entry = MemoryEntry(key=args["key"], value=args["value"], asset_type=args.get("asset_type", AssetType.FACT.value), category=args.get("category","fact"), confidence=args.get("confidence",1.0), status=MemoryStatus.PROPOSED.value, visibility=args.get("visibility", MemoryVisibility.PRIVATE.value), project_id=args["project_id"], agent_id=args["agent_id"], source_ref=args.get("source_ref",""), expires_at=expires, created_by=args["agent_id"], tags=args.get("tags",[]))
    store = _init_store()
    store.store(entry)
    return {"key": entry.key, "status": entry.status, "project_id": entry.project_id}

def handle_promote_memory(args):
    store = _init_store()
    ok = store.transition(project_id=args["project_id"], key=args["key"], new_status=args["new_status"], actor_id=args.get("actor_id",""))
    if ok: return {"success": True, "key": args["key"], "new_status": args["new_status"]}
    return {"success": False, "reason": "Transition not allowed or entry not found"}

def handle_forget_memory(args):
    store = _init_store()
    deleted = store.delete(project_id=args["project_id"], key=args["key"])
    return {"deleted": deleted, "key": args["key"]}

HANDLERS["search_hub"] = handle_search_hub
HANDLERS["context_bundle"] = handle_context_bundle
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