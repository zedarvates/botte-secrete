"""Cooperative TCP/HTTP evidence without payloads, credentials or raw targets."""

from __future__ import annotations

import ipaddress
import re
import time
import urllib.error
import urllib.parse
from contextlib import contextmanager

from skills.capabilities.observations import _CALL, _SESSION

MAX_NETWORK = 256


def _target(session, scheme: str, host: str, port) -> dict:
    """Caller holds the session lock. Labels are local to this report, no DNS."""
    host = (host or "").lower().strip("[]")
    if host == "localhost":
        kind = "loopback"
    else:
        try:
            ip = ipaddress.ip_address(host)
            kind = "loopback" if ip.is_loopback else "private" if ip.is_private else "public"
        except ValueError:
            kind = "hostname" if host else "unknown"
    key = (scheme, host, port)
    if key not in session._targets:
        session._targets[key] = f"t{len(session._targets) + 1}"
    return {"id": session._targets[key], "scheme": scheme, "address_kind": kind}


def _http_target(session, url: str) -> dict:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            port = parsed.port
            return _target(session, parsed.scheme, parsed.hostname,
                           port if port is not None else (443 if parsed.scheme == "https" else 80))
    except (ValueError, TypeError):
        pass
    return _target(session, "unknown", "", None)


def compare_network(record: dict, declaration_status: str) -> str:
    """A transport response is a narrow facet, never a remote-effect verdict."""
    responded = (record["http_status"] is not None if record["transport"] == "http"
                 else record["status"] == "returned")
    return ("supported" if responded and declaration_status == "declared"
            and record["effect_ref"] is not None else "unknown")


class NetworkEvidence:
    def __init__(self, session=None, record=None):
        self.session, self.record = session, record

    def response(self, response) -> None:
        if self.record is None:
            return
        # Intentionally avoid headers, content and exception strings. A custom
        # response without metadata leaves those facts unknown.
        try:
            code = response.getcode()
            url = response.geturl()
        except (AttributeError, ValueError, TypeError, OSError):
            return
        with self.session._lock:
            if self.session._closed:
                return
            if type(code) is int and 100 <= code <= 599:
                self.record["http_status"] = code
            if isinstance(url, str):
                target = _http_target(self.session, url)
                self.record["response_target"] = target
                if target["scheme"] != "unknown" and self.record["target"]["scheme"] != "unknown":
                    self.record["origin_changed"] = target != self.record["target"]
            call = next(c for c in self.session.report["calls"] if c["id"] == self.record["call_id"])
            self.record["comparison"] = compare_network(self.record, call["declaration_status"])
            self.session.flush()

    def read_complete(self) -> None:
        if self.record is not None:
            with self.session._lock:
                if self.session._closed:
                    return
                self.record["response_complete"] = True
                self.session.flush()


@contextmanager
def network_attempt(transport: str, destination, effect_ref: str, *, method: str):
    """Wrap the real transport call/read; perform no network operation itself.

    HTTP destination is a Request; TCP destination is (host, port). References
    and methods come from reviewed instrumentation, never a declaration command.
    """
    session, call_id = _SESSION.get(), _CALL.get()
    if session is None or call_id is None or session._closed:
        yield NetworkEvidence()
        return
    with session._lock:
        if session._closed:
            record = None
        elif len(session.report["network"]) >= MAX_NETWORK:
            session.problem("network observation limit reached; further attempts unassessed")
            session.flush()
            record = None
        else:
            call = next(c for c in session.report["calls"] if c["id"] == call_id)
            contract = session.report["declarations"].get(call["declaration_ref"], {})
            match = re.fullmatch(r"/(expected_effects|downstream_effects)/([0-9]+)", effect_ref)
            if match is None or int(match[2]) >= len(contract.get(match[1], [])):
                effect_ref = None
            target = (_http_target(session, destination.full_url) if transport == "http"
                      else _target(session, "tcp", *destination))
            record = {"id": f"n{len(session.report['network']) + 1}", "call_id": call_id,
                      "transport": transport, "method": method, "target": target,
                      "effect_ref": effect_ref, "facet": "transport_response",
                      "status": "running", "http_status": None, "response_target": None,
                      "origin_changed": None,
                      "response_complete": False if transport == "http" else None,
                      "duration_ms": None, "error_kind": None, "comparison": "unknown",
                      "remote_effects": "unknown"}
            session.report["network"].append(record)
            session.flush()
    if record is None:
        yield NetworkEvidence()
        return
    evidence = NetworkEvidence(session, record)
    start = time.monotonic()
    error = None
    try:
        yield evidence
    except BaseException as exc:
        if isinstance(exc, urllib.error.HTTPError):
            evidence.response(exc)
            error = "http_error"
        elif isinstance(exc, TimeoutError) or (
                isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)):
            error = "timeout"
        elif isinstance(exc, (urllib.error.URLError, OSError)):
            error = "network_error"
        else:
            error = "response_error" if isinstance(exc, Exception) else "interrupted"
        raise
    finally:
        with session._lock:
            record["status"] = "raised" if error else "returned"
            record["error_kind"] = error
            record["duration_ms"] = max(0, round((time.monotonic() - start) * 1000))
            record["comparison"] = compare_network(record, call["declaration_status"])
            session.flush()
