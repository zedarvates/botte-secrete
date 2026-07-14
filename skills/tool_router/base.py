"""Safe, dependency-free tool routing contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


def _words(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold(), flags=re.UNICODE))


@dataclass(frozen=True)
class ToolSpec:
    """The subset of JSON Schema needed to validate an executable tool call."""

    name: str
    description: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("tool parameters must be a mapping")

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class ToolRouteResult:
    tool_name: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    confidence: float = 0.0
    executable: bool = False
    reason: str | None = None

    @property
    def abstained(self) -> bool:
        return self.tool_name is None

    @classmethod
    def abstain(cls, source: str, reason: str) -> "ToolRouteResult":
        return cls(source=source, reason=reason)


class ToolRouter(Protocol):
    def route(self, query: str, tools: Sequence[ToolSpec]) -> ToolRouteResult:
        """Return a safe route or an explicit abstention; never execute a tool."""


def validate_route(
    tool_name: str | None, arguments: Any, tools: Sequence[ToolSpec], *, source: str, confidence: float = 0.0
) -> ToolRouteResult:
    """Validate an untrusted route against the offered schemas.

    Unsupported/nested schema types deliberately fail closed.  A model may suggest
    a candidate, but only a validated result is marked executable.
    """
    if not isinstance(tool_name, str):
        return ToolRouteResult.abstain(source, "missing_tool_name")
    by_name = {tool.name: tool for tool in tools}
    tool = by_name.get(tool_name)
    if tool is None:
        return ToolRouteResult.abstain(source, "tool_not_allowed")
    if not isinstance(arguments, Mapping):
        return ToolRouteResult.abstain(source, "arguments_not_object")
    schema = tool.parameters
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        return ToolRouteResult.abstain(source, "invalid_tool_schema")
    if any(name not in arguments for name in required):
        return ToolRouteResult.abstain(source, "missing_required_argument")
    if schema.get("additionalProperties") is False and any(name not in properties for name in arguments):
        return ToolRouteResult.abstain(source, "unexpected_argument")
    for name, value in arguments.items():
        definition = properties.get(name)
        if definition is None:
            continue
        if not isinstance(definition, Mapping) or not _primitive_matches(value, definition.get("type")):
            return ToolRouteResult.abstain(source, "invalid_argument_type")
    return ToolRouteResult(tool.name, dict(arguments), source, max(0.0, min(1.0, confidence)), True)


def _primitive_matches(value: Any, expected: Any) -> bool:
    checks = {
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }
    return isinstance(expected, str) and expected in checks and checks[expected]()


class LexicalToolRouter:
    """A deterministic, zero-token selector. It never fabricates arguments."""

    def route(self, query: str, tools: Sequence[ToolSpec]) -> ToolRouteResult:
        if not isinstance(query, str) or not query.strip():
            return ToolRouteResult.abstain("lexical", "empty_query")
        if not tools:
            return ToolRouteResult.abstain("lexical", "no_tools")
        query_words = _words(query)
        ranked = []
        for tool in tools:
            name_words = _words(tool.name.replace("_", " ").replace("-", " "))
            score = 3 * len(query_words & name_words) + len(query_words & _words(tool.description))
            ranked.append((score, tool.name, tool))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        if ranked[0][0] <= 0:
            return ToolRouteResult.abstain("lexical", "no_lexical_match")
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return ToolRouteResult.abstain("lexical", "ambiguous_lexical_match")
        tool = ranked[0][2]
        return validate_route(tool.name, {}, tools, source="lexical", confidence=1.0)
