"""Versioned contract shared by the HTTP API, MCP bridge and local service.

The validator intentionally supports only the JSON Schema subset emitted here.
No agent identity, trust class or execution authority is accepted in tool input.
"""
from __future__ import annotations

import json
import math
import re

CONTRACT_VERSION = "botte.shared-memory/v1"
MAX_BODY = 262_144


def obj(properties, required=()):
    return {"type": "object", "properties": properties,
            "required": list(required), "additionalProperties": False}


def string(max_length=512, **extra):
    return {"type": "string", "minLength": 1, "maxLength": max_length, **extra}


IDENTIFIER = string(128, pattern=r"^[A-Za-z0-9_][A-Za-z0-9._:-]{0,127}$")
PROJECT = string(128, pattern=r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
VERSION = {"type": "integer", "minimum": 1, "maximum": 2**53 - 1}
TIMESTAMP = {"type": "number", "exclusiveMinimum": 0, "maximum": 32_503_680_000}
EMBEDDING = obj({
    "model": string(128),
    "vector": {"type": "array", "minItems": 1, "maxItems": 4096,
               "items": {"type": "number", "minimum": -1_000_000,
                         "maximum": 1_000_000}},
}, ("model", "vector"))
SOURCE = obj({
    "type": string(enum=["user", "repo", "web", "tool", "agent", "generated"]),
    "id": string(), "uri": string(), "run_id": IDENTIFIER,
    "observed_at": TIMESTAMP, "excerpt": string(16_000),
}, ("type", "id", "run_id", "observed_at", "excerpt"))
RECORD = obj({
    "text": string(16_000),
    "kind": string(enum=["fact", "decision", "preference", "observation",
                         "checkpoint", "procedure"]),
    "source": SOURCE,
    "visibility": string(enum=["private", "project"]),
    "expires_at": TIMESTAMP,
    "subject_ref": string(),
    "evidence_refs": {"type": "array", "maxItems": 20, "items": string()},
    "tags": {"type": "array", "maxItems": 20, "items": string(64)},
    "embedding": EMBEDDING,
}, ("text", "kind", "source"))

_write = {"project_id": PROJECT, "key": IDENTIFIER, "request_id": IDENTIFIER}
_read = {"project_id": PROJECT,
         "query": {"type": "string", "maxLength": 2000},
         "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         "max_bytes": {"type": "integer", "minimum": 1024, "maximum": 65_536}}
SCHEMAS = {
    "capture": obj({**_write, "record": RECORD}, (*_write, "record")),
    "correct": obj({**_write, "record": RECORD, "expected_version": VERSION},
                   (*_write, "record", "expected_version")),
    "checkpoint": obj({**_write, "record": RECORD}, (*_write, "record")),
    "forget": obj({**_write, "expected_version": VERSION},
                  (*_write, "expected_version")),
    "review": obj({**_write, "expected_version": VERSION,
                   "new_status": string(enum=["review_active", "promoted",
                                               "obsoleted", "expired"])},
                  (*_write, "expected_version", "new_status")),
    "recall": obj({**_read, "area": string(enum=["context", "observations"]),
                   "embedding": EMBEDDING}, ("project_id",)),
    "history": obj({"project_id": PROJECT, "key": IDENTIFIER},
                   ("project_id", "key")),
    "scribe": obj({"project_id": PROJECT, "record": RECORD},
                  ("project_id", "record")),
    "wiki": obj(_read, ("project_id",)),
}
DESCRIPTIONS = {
    "capture": "Capture sourced data as a proposal; external observations stay quarantined.",
    "correct": "Replace the owned current version atomically; keep history and reset review.",
    "checkpoint": "Capture a sourced work checkpoint; no proof or permission is inferred.",
    "forget": "Delete current data, revisions, vectors and receipts; prevent replay resurrection.",
    "review": "Advance trusted-user data through review; cannot promote quarantined data.",
    "recall": "Retrieve cited current context, or explicitly inspect quarantined observations.",
    "history": "Read revision history as the owner or a configured curator.",
    "scribe": "Suggest nearest memories for review; never merge, promote or train automatically.",
    "wiki": "Render a current, cited Markdown view; writes no files and creates no cache.",
}
READ_ONLY = frozenset({"recall", "history", "scribe", "wiki"})


def validate(schema, value, path="arguments"):
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str,
             "integer": int, "number": (int, float)}
    if kind in types and (not isinstance(value, types[kind])
                         or kind in {"integer", "number"} and isinstance(value, bool)):
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if kind == "object":
        if set(value) - set(schema["properties"]):
            raise ValueError(f"{path}: unknown fields")
        if set(schema["required"]) - set(value):
            raise ValueError(f"{path}: required fields missing")
        for key, item in value.items():
            validate(schema["properties"][key], item, f"{path}.{key}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema["maxItems"]:
            raise ValueError(f"{path}: invalid array length")
        for item in value:
            validate(schema["items"], item, f"{path}[]")
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema["maxLength"]:
            raise ValueError(f"{path}: invalid string length")
        if schema.get("minLength", 0) and not value.strip():
            raise ValueError(f"{path}: empty text")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError(f"{path}: control characters are not allowed")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{path}: invalid identifier")
    elif kind in {"integer", "number"}:
        if not math.isfinite(value):
            raise ValueError(f"{path}: expected a finite number")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path}: below exclusive minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path}: above maximum")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non-finite JSON number")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def tools():
    return [{"name": "memory_" + name, "description": DESCRIPTIONS[name],
             "inputSchema": schema,
             "annotations": {"readOnlyHint": name in READ_ONLY,
                             "destructiveHint": name in {"correct", "forget"},
                             "openWorldHint": False}}
            for name, schema in SCHEMAS.items()]


def openapi():
    return {"openapi": "3.1.0", "info": {"title": "Botte shared memory",
            "version": "0.1.0"}, "security": [{"bearerAuth": []}],
            "components": {"securitySchemes": {"bearerAuth": {
                "type": "http", "scheme": "bearer"}}},
            "paths": {"/v1/memory/" + name: {"post": {
                "operationId": "memory_" + name, "description": DESCRIPTIONS[name],
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": schema}}},
                "responses": {str(code): {"description": description} for code, description
                              in [(200, "Structured result"), (400, "Invalid input"),
                                  (401, "Unauthenticated"), (403, "Forbidden"),
                                  (404, "Not found"), (409, "Version or replay conflict"),
                                  (413, "Request too large"), (503, "Temporarily unavailable")]}
            }} for name, schema in SCHEMAS.items()}}
