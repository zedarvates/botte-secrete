"""Bounded exploration of explicitly allowed interface actions.

``explore_interface(adapter, scope=..., allowed_actions=[...])`` accepts an
adapter with ``reset()``, ``observe()`` and ``perform(action_id)``. Observations
contain ``state_id``, ``scope``, ``actions`` (IDs) and optional ``terminal``.
Actions return None or ``{status: 'ok'|'failed', reason?: str}``.

Reset and path replay make traversal reproducible; replay actions count toward
the same budget. Generic callbacks are trusted Python and must enforce their
own hard timeouts. The explorer checks a cooperative deadline between callbacks
and rejects results returned after it. No global coverage or GUI qualification
is inferred from a finite state graph.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import time
from collections import deque
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


def _identifier(value: object, name: str) -> str:
    if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f"{name} must be a nonempty bounded identifier")
    return value


def _identifiers(values: object, name: str, limit: int = 256) -> list[str]:
    if not isinstance(values, (list, tuple)) or len(values) > limit:
        raise ValueError(f"{name} must be a bounded list")
    result = [_identifier(value, name) for value in values]
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class _Stop(Exception):
    pass


def explore_interface(adapter, *, scope: str, allowed_actions: list[str],
                      goals: list[str] | tuple[str, ...] = (),
                      max_actions: int = 64, max_states: int = 32,
                      max_seconds: float = 10.0) -> dict:
    """Explore observed, allowed edges; report failures and incomplete evidence.

    ``completed`` means the observed allowed frontier was exhausted, not that
    the program is correct or that all possible application states were found.
    Unobserved goals are never declared globally unreachable.
    """
    scope = _identifier(scope, "scope")
    allowed = set(_identifiers(allowed_actions, "allowed_actions"))
    goals = _identifiers(goals, "goals")
    for name, value, lower, upper in (("max_actions", max_actions, 0, 4096),
                                      ("max_states", max_states, 1, 1024)):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"{name} outside supported range")
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not 0 < max_seconds <= 300 or not math.isfinite(max_seconds)):
        raise ValueError("max_seconds must be finite and in (0, 300]")
    if any(not callable(getattr(adapter, name, None)) for name in ("reset", "observe", "perform")):
        raise ValueError("adapter must provide reset, observe and perform methods")
    started = time.monotonic()
    deadline = started + max_seconds
    states: dict[str, dict] = {}
    paths: dict[str, list[tuple[str, str, str]]] = {}
    transitions: list[dict] = []
    issues: list[dict] = []
    frontier: deque[tuple[str, str]] = deque()
    counts = {"actions": 0, "replay_actions": 0, "resets": 0, "observations": 0}
    root: str | None = None
    stop_reason = "frontier_exhausted"
    current_edge: tuple[str, str] | None = None

    def invoke(function, *args):
        if time.monotonic() >= deadline:
            raise _Stop("duration_budget")
        try:
            value = function(*args)
        except TimeoutError:
            raise _Stop("adapter_timeout") from None
        except Exception as error:
            issues.append({"kind": "adapter_error", "exception": type(error).__name__})
            raise _Stop("adapter_error") from None
        if time.monotonic() >= deadline:
            raise _Stop("duration_budget")
        return value

    def observe() -> dict:
        raw = invoke(adapter.observe)
        counts["observations"] += 1
        if not isinstance(raw, dict):
            raise _Stop("invalid_observation")
        try:
            sid = _identifier(raw.get("state_id"), "state_id")
            observed_scope = _identifier(raw.get("scope"), "observed scope")
            actions = _identifiers(raw.get("actions"), "observed actions", 64)
        except ValueError:
            raise _Stop("invalid_observation") from None
        if observed_scope != scope:
            raise _Stop("scope_mismatch")
        terminal = raw.get("terminal", False)
        if type(terminal) is not bool:
            raise _Stop("invalid_observation")
        return {"state_id": sid, "actions": actions, "terminal": terminal}

    def record(observation: dict, path: list[tuple[str, str, str]]) -> None:
        sid = observation["state_id"]
        summary = {**observation, "excluded_actions": [a for a in observation["actions"]
                                                       if a not in allowed]}
        if sid in states:
            if states[sid] != summary:
                raise _Stop("unstable_state_identity")
            return
        if len(states) >= max_states:
            raise _Stop("state_budget")
        states[sid] = summary
        paths[sid] = path
        frontier.extend((sid, action) for action in observation["actions"] if action in allowed)

    def perform(action: str, *, replay: bool) -> dict:
        if counts["actions"] >= max_actions:
            raise _Stop("action_budget")
        counts["actions"] += 1
        if replay:
            counts["replay_actions"] += 1
        result = invoke(adapter.perform, action)
        if result is None:
            return {"status": "ok"}
        if not isinstance(result, dict) or result.get("status") not in ("ok", "failed"):
            raise _Stop("invalid_action_result")
        if result["status"] == "failed":
            reason = result.get("reason")
            if not isinstance(reason, str) or len(reason.encode("utf-8")) > 256:
                reason = "adapter_reported_failure"
            return {"status": "failed", "reason": reason}
        return {"status": "ok"}

    def reset() -> dict:
        counts["resets"] += 1
        invoke(adapter.reset)
        return observe()

    try:
        initial = reset()
        root = initial["state_id"]
        record(initial, [])
        while frontier:
            sid, action = frontier.popleft()
            current_edge = (sid, action)
            initial = reset()
            if initial["state_id"] != root:
                raise _Stop("reset_state_changed")
            record(initial, [])
            for source, previous_action, expected in paths[sid]:
                result = perform(previous_action, replay=True)
                if result["status"] == "failed":
                    issues.append({"kind": "replay_failed", "state_id": source,
                                   "action": previous_action, "reason": result["reason"]})
                    raise _Stop("replay_failed")
                observed = observe()
                if observed["state_id"] != expected:
                    issues.append({"kind": "replay_mismatch", "expected": expected,
                                   "observed": observed["state_id"]})
                    raise _Stop("replay_mismatch")
                record(observed, paths[expected])
            result = perform(action, replay=False)
            if result["status"] == "failed":
                transitions.append({"source": sid, "action": action, **result})
            else:
                observed = observe()
                target = observed["state_id"]
                transitions.append({"source": sid, "action": action, "target": target,
                                    "status": "observed", "state_changed": sid != target})
                record(observed, paths[sid] + [(sid, action, target)])
            current_edge = None
    except _Stop as stop:
        stop_reason = str(stop)
        issues.append({"kind": stop_reason})
        if current_edge is not None:
            frontier.appendleft(current_edge)

    exhausted = stop_reason == "frontier_exhausted"
    failures = sum(row["status"] == "failed" for row in transitions)
    status = "failed" if failures else ("completed" if exhausted else "incomplete")
    kind = getattr(adapter, "kind", "custom")
    if not isinstance(kind, str) or len(kind) > 64:
        kind = "custom"
    state_rows = list(states.values())
    graph = {"scope": scope, "root": root, "states": state_rows, "transitions": transitions}
    return {"schema": "parcimonia.interface-exploration/v1", "status": status,
            "adapter_kind": kind, "scope": scope, "root": root,
            "states": state_rows, "transitions": transitions, "issues": issues,
            "dead_ends": [row["state_id"] for row in state_rows
                          if not row["actions"] and not row["terminal"]],
            "coverage": {"allowed_frontier_exhausted": exhausted, "global": "unknown",
                         "goals_observed": [goal for goal in goals if goal in states],
                         "goals_not_observed": [goal for goal in goals if goal not in states],
                         "pending_edges": len(frontier),
                         "excluded_actions": sum(len(row["excluded_actions"]) for row in state_rows)},
            "budget": {"max_actions": max_actions, "max_states": max_states,
                       "max_seconds": max_seconds, **counts, "stop_reason": stop_reason},
            "provenance": {"graph_sha256": _digest(graph),
                           "allowed_actions_sha256": _digest(sorted(allowed))},
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "boundaries": {"graphical_qualification": False, "global_reachability_proved": False,
                           "callback_timeout": "adapter_enforced; cooperative outer deadline"}}


class DeclarativeAdapter:
    """Replay a caller-supplied model; this does not test a live application.

    Model: {scope, initial_state, states: {id: {actions: {action: target_or_null},
    terminal?: bool}}}. Null targets represent declared transition failures.
    """

    kind = "model_replay"

    def __init__(self, model: dict):
        if not isinstance(model, dict):
            raise ValueError("model must be an object")
        raw = json.dumps(model, allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(raw) > 128 * 1024:
            raise ValueError("model exceeds 128 KiB")
        self.model = json.loads(raw)
        self.scope = _identifier(self.model.get("scope"), "scope")
        self.initial = _identifier(self.model.get("initial_state"), "initial_state")
        states = self.model.get("states")
        if not isinstance(states, dict) or not 1 <= len(states) <= 1024:
            raise ValueError("model needs bounded states")
        for sid, state in states.items():
            _identifier(sid, "state_id")
            if not isinstance(state, dict) or not isinstance(state.get("actions"), dict):
                raise ValueError("state needs an action map")
            _identifiers(list(state["actions"]), "actions", 64)
            if type(state.get("terminal", False)) is not bool:
                raise ValueError("terminal must be boolean")
            for target in state["actions"].values():
                if target is not None and (not isinstance(target, str) or target not in states):
                    raise ValueError("action target must name a declared state or null")
        if self.initial not in states:
            raise ValueError("initial_state is not declared")
        self.reset()

    def reset(self) -> None:
        self.current = self.initial

    def observe(self) -> dict:
        state = self.model["states"][self.current]
        return {"state_id": self.current, "scope": self.scope,
                "actions": list(state["actions"]), "terminal": state.get("terminal", False)}

    def perform(self, action_id: str) -> dict:
        actions = self.model["states"][self.current]["actions"]
        if action_id not in actions:
            raise ValueError("action not available in current state")
        target = actions[action_id]
        if target is None:
            return {"status": "failed", "reason": "declared_transition_failure"}
        self.current = target
        return {"status": "ok"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirects are outside the explicit navigation scope")


class _NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.state = None
        self.scope = None
        self.terminal = False
        self.links: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "meta" and fields.get("name") in ("parcimonia-state", "parcimonia-scope"):
            name = fields["name"].split("-")[-1]
            if getattr(self, name) is not None:
                raise ValueError("duplicate state/scope metadata")
            setattr(self, name, fields.get("content"))
        if tag == "meta" and fields.get("name") == "parcimonia-terminal":
            if fields.get("content") not in ("true", "false"):
                raise ValueError("invalid terminal metadata")
            self.terminal = fields["content"] == "true"
        if tag == "a" and "data-action" in fields:
            action = _identifier(fields["data-action"], "action_id")
            if action in self.links or len(self.links) >= 64:
                raise ValueError("duplicate or excessive navigation actions")
            if not isinstance(fields.get("href"), str):
                raise ValueError("navigation action requires href")
            self.links[action] = fields["href"]


class LoopbackHttpAdapter:
    """Navigate an explicitly scoped local HTML test interface using GET.

    Pages expose ``parcimonia-state``/``parcimonia-scope`` meta tags and links
    ``<a data-action="next" href="/next">``. Only literal loopback IP origins
    and exact caller-listed paths are admitted. Proxies, redirects, queries,
    fragments and credentials are refused. GET is not a guarantee of absence
    of effects: use only a caller-controlled test application.
    """

    kind = "http_navigation"

    def __init__(self, initial_url: str, *, scope: str, allowed_paths: list[str],
                 timeout: float = 1.0):
        self.scope = _identifier(scope, "scope")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not 0 < timeout <= 5 or not math.isfinite(timeout)):
            raise ValueError("timeout must be in (0, 5]")
        self.timeout = timeout
        parts = urlsplit(initial_url)
        try:
            address = ipaddress.ip_address(parts.hostname or "")
            port = parts.port
        except ValueError:
            raise ValueError("URL must use a literal loopback IP and valid port") from None
        if (parts.scheme != "http" or not address.is_loopback or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or any(ord(char) <= 32 or ord(char) == 127 for char in initial_url)):
            raise ValueError("only scoped loopback HTTP test URLs are supported")
        self.origin = (parts.scheme, address.compressed, port or 80)
        if (not isinstance(allowed_paths, list) or not 1 <= len(allowed_paths) <= 256
                or any(not isinstance(path, str) or not path.startswith("/")
                       or path.startswith("//") or urlsplit(path).query or urlsplit(path).fragment
                       or any(ord(char) <= 32 or ord(char) == 127 for char in path)
                       for path in allowed_paths)):
            raise ValueError("allowed_paths must explicitly list local paths")
        self.allowed_paths = frozenset(allowed_paths)
        self.initial_url = initial_url
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._observation = None
        self._links: dict[str, str] = {}
        self.current_url = initial_url
        self._validate_url(initial_url)

    def _validate_url(self, url: str) -> None:
        parts = urlsplit(url)
        try:
            origin = (parts.scheme, ipaddress.ip_address(parts.hostname or "").compressed,
                      parts.port or 80)
        except ValueError:
            raise ValueError("navigation target is outside the allowed origin") from None
        if (origin != self.origin or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or (parts.path or "/") not in self.allowed_paths
                or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
            raise ValueError("navigation target is outside the explicit origin/path scope")

    def _load(self, url: str) -> None:
        self._validate_url(url)
        request = Request(url, headers={"Accept": "text/html"}, method="GET")
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError("navigation response exceeds 128 KiB")
            content_type = response.headers.get_content_type()
            if content_type != "text/html":
                raise ValueError("navigation response must be text/html")
        parser = _NavigationParser()
        parser.feed(raw.decode("utf-8"))
        parser.close()
        observation = {"state_id": _identifier(parser.state, "state_id"),
                       "scope": _identifier(parser.scope, "scope"),
                       "actions": list(parser.links), "terminal": parser.terminal}
        links = {action: urljoin(url, href) for action, href in parser.links.items()}
        # Link filtering belongs the explicit explorer action allowlist. Even an
        # excluded external link remains visible, and is never fetched here.
        self.current_url, self._links, self._observation = url, links, observation

    def reset(self) -> None:
        self._load(self.initial_url)

    def observe(self) -> dict:
        if self._observation is None:
            raise ValueError("reset must precede observation")
        return {**self._observation, "actions": list(self._observation["actions"])}

    def perform(self, action_id: str) -> dict:
        if action_id not in self._links:
            raise ValueError("action not available in current state")
        target = self._links[action_id]
        self._validate_url(target)
        try:
            self._load(target)
        except HTTPError as error:
            return {"status": "failed", "reason": f"http_status_{error.code}"}
        return {"status": "ok"}
