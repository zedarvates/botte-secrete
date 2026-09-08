"""The small closed schema used by effect observation transport."""

from __future__ import annotations

import re


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items, limit):
    return {"type": "array", "items": items, "maxItems": limit}


TEXT = {"type": "string", "minLength": 1, "maxLength": 8192}
NULL_TEXT = {"type": ["string", "null"], "minLength": 1, "maxLength": 8192}
HASH = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
INTEGER = {"type": ["integer", "null"], "minimum": 0}
STATE = obj({"state": {"enum": ["present", "missing", "unknown"]},
             "sha256": HASH, "size": INTEGER})
CALL = obj({"id": TEXT, "parent_id": NULL_TEXT, "capability_id": NULL_TEXT,
            "operation": TEXT, "source_path": TEXT,
            "context": {"type": "object", "properties": {
                "fresh": {"type": "boolean"}, "scan_subnet": {"type": "boolean"}},
                "additionalProperties": False},
            "status": {"enum": ["running", "returned", "raised"]},
            "duration_ms": INTEGER,
            "declaration_status": {"enum": ["declared", "stale", "missing", "invalid"]},
            "declaration_ref": HASH})
OBSERVATION = obj({"id": TEXT, "call_id": TEXT, "resource": TEXT,
                   "effect_ref": {"type": ["string", "null"],
                                  "pattern": "^/(expected_effects|downstream_effects)/[0-9]+$"},
                   "facet": {"enum": ["file_present_after_write"]},
                   "write_status": {"enum": ["running", "returned", "raised"]},
                   "before": STATE, "after": STATE,
                   "comparison": {"enum": ["supported", "deviation", "unknown"]}})
REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Botte effect observations v1",
    **obj({"schema": {"enum": ["botte.effect-observations/v1"]},
           "run_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
           "context": obj({"started_at": TEXT, "cwd": TEXT, "python": TEXT}),
           "process": obj({"status": {"enum": ["running", "exited", "timed_out", "launch_failed",
                                                 "not_run", "runner_error"]},
                           "exit_code": {"type": ["integer", "null"]}}),
           "calls": array(CALL, 128),
           "declarations": {"type": "object", "maxProperties": 128,
                            "additionalProperties": {"type": "object"}},
           "observations": array(OBSERVATION, 256),
           "problems": array(TEXT, 32), "limitations": array(TEXT, 32)})}


def validate_shape(value, schema, path="$", errors=None):
    """Validate the bounded keyword subset above; no remote refs or evaluation."""
    errors = [] if errors is None else errors
    types = {"object": lambda x: isinstance(x, dict),
             "array": lambda x: isinstance(x, list),
             "string": lambda x: isinstance(x, str),
             "integer": lambda x: type(x) is int,
             "boolean": lambda x: type(x) is bool,
             "null": lambda x: x is None}
    expected = schema.get("type")
    if expected:
        expected = [expected] if isinstance(expected, str) else expected
        if not any(types[t](value) for t in expected):
            errors.append(f"{path}: invalid type")
            return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: invalid choice")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if len(value) > schema.get("maxProperties", 10000):
            errors.append(f"{path}: too many properties")
        if any(key not in value for key in schema.get("required", [])):
            errors.append(f"{path}: missing fields")
        for key, item in value.items():
            if key in properties:
                validate_shape(item, properties[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unknown field")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_shape(item, schema["additionalProperties"], f"{path}.{key}", errors)
    elif isinstance(value, list):
        if len(value) > schema.get("maxItems", 10000):
            errors.append(f"{path}: too many items")
        for index, item in enumerate(value):
            validate_shape(item, schema.get("items", {}), f"{path}[{index}]", errors)
    elif isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 1000000):
            errors.append(f"{path}: invalid length")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: invalid pattern")
    elif type(value) is int and value < schema.get("minimum", value):
        errors.append(f"{path}: below minimum")
    return errors
