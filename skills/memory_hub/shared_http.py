"""Loopback HTTP pilot and authenticated client; no third-party dependency.

Use an authenticated TLS reverse proxy or SSH tunnel for remote access. The
stdlib pilot deliberately refuses non-loopback binds and browser Origins.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from skills.memory_hub.shared_contract import MAX_BODY, SCHEMAS, decode, encode, openapi
from skills.memory_hub.shared_service import MemoryService, Principal, ServiceError


def read_token(path):
    path = Path(path)
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("Token file must be readable only by its owner")
    token = path.read_text(encoding="utf-8").strip()
    if not 32 <= len(token) <= 512 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Token must contain 32-512 non-whitespace ASCII characters")
    return token


class AuthRegistry:
    def __init__(self, principals):
        self.principals = principals

    @classmethod
    def load(cls, config_path):
        path = Path(config_path).resolve()
        config = decode(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or set(config) != {"schema", "principals"}:
            raise ValueError("Invalid authentication configuration")
        if config["schema"] != "botte.memory-auth/v1" or not isinstance(config["principals"], list):
            raise ValueError("Unsupported authentication configuration")
        if not 1 <= len(config["principals"]) <= 100:
            raise ValueError("Configure 1-100 explicit principals")
        principals, actors = {}, set()
        for item in config["principals"]:
            if not isinstance(item, dict) or set(item) != {"actor_id", "projects", "rights", "token_file"}:
                raise ValueError("Invalid principal configuration")
            if not isinstance(item["projects"], list) or not isinstance(item["rights"], list):
                raise ValueError("Principal projects and rights must be arrays")
            principal = Principal(item["actor_id"], frozenset(item["projects"]), frozenset(item["rights"]))
            if principal.actor_id in actors:
                raise ValueError("Duplicate actor identity")
            actors.add(principal.actor_id)
            token = read_token(path.parent / item["token_file"])
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            if digest in principals:
                raise ValueError("Each principal requires a unique token")
            principals[digest] = principal
        return cls(principals)

    def authenticate(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise ServiceError("unauthenticated", "Bearer authentication required", 401)
        token = authorization[7:]
        if len(token) > 512 or not token.isascii():
            raise ServiceError("unauthenticated", "Invalid bearer token", 401)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        for candidate, principal in self.principals.items():
            if hmac.compare_digest(digest, candidate):
                return principal
        raise ServiceError("unauthenticated", "Invalid bearer token", 401)


class MemoryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service, auth):
        if address[0] not in {"127.0.0.1", "localhost"}:
            raise ValueError("The pilot binds only to IPv4 loopback; use a TLS proxy or SSH tunnel")
        self.service, self.auth = service, auth
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, MemoryHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class MemoryHandler(BaseHTTPRequestHandler):
    server_version = "BotteMemory/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, _format, *args):
        # Requests, source text and credentials must not enter access logs.
        pass

    def _principal(self):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }:
            raise ServiceError("invalid_host", "Expected the loopback Host header", 403)
        if self.headers.get("Origin") is not None:
            raise ServiceError("browser_origin", "Browser origins are not enabled for this pilot", 403)
        authorization = self.headers.get_all("Authorization", [])
        if len(authorization) != 1:
            raise ServiceError("unauthenticated", "One bearer token is required", 401)
        return self.server.auth.authenticate(authorization[0])

    def _send(self, status, payload):
        body = encode(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, post):
        try:
            principal = self._principal()
            if not post:
                if self.path == "/health":
                    result = {"status": "ready", "backend": "sqlite", "cloud_calls": False}
                elif self.path == "/openapi.json":
                    result = openapi()
                else:
                    raise ServiceError("not_found", "Unknown endpoint", 404)
            else:
                prefix = "/v1/memory/"
                operation = self.path[len(prefix):] if self.path.startswith(prefix) else ""
                if operation not in SCHEMAS:
                    raise ServiceError("not_found", "Unknown endpoint", 404)
                if self.headers.get("Transfer-Encoding") is not None:
                    raise ServiceError("invalid_input", "Transfer-Encoding is not accepted")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ServiceError("invalid_input", "A single Content-Length is required")
                length = int(lengths[0])
                if not 0 < length <= MAX_BODY:
                    raise ServiceError("too_large", "Request too large or empty", 413)
                if self.headers.get_content_type() != "application/json":
                    raise ServiceError("invalid_input", "Content-Type must be application/json", 415)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ServiceError("invalid_input", "Incomplete request body")
                result = self.server.service.call(operation, decode(body), principal)
            self._send(200, {"ok": True, "result": result})
        except ServiceError as error:
            self._send(error.status, {"ok": False, "error": {"code": error.code, "message": error.message}})
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            self._send(400, {"ok": False, "error": {"code": "invalid_input", "message": "Invalid JSON input"}})
        except sqlite3.OperationalError:
            self._send(503, {"ok": False, "error": {"code": "storage_unavailable", "message": "Storage temporarily unavailable"}})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            self._send(500, {"ok": False, "error": {"code": "internal_error", "message": "Internal service error"}})

    def do_POST(self):
        self._handle(True)

    def do_GET(self):
        self._handle(False)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MemoryHTTPClient:
    def __init__(self, url, token):
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Use a bare memory service origin without credentials, path or query")
        local = parsed.hostname == "localhost"
        try:
            local = local or ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            pass
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ValueError("Remote memory requires HTTPS; HTTP is allowed only for loopback")
        if not parsed.hostname:
            raise ValueError("Memory service host is required")
        self.url, self.token = url.rstrip("/"), token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def call(self, operation, args):
        if operation not in SCHEMAS:
            raise ServiceError("unknown_operation", "Unknown memory operation", 404)
        request = urllib.request.Request(self.url + "/v1/memory/" + operation,
            data=encode(args), headers={"Authorization": "Bearer " + self.token,
                                       "Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(request, timeout=15) as response:
                status = response.status
                body = response.read(MAX_BODY + 1)
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise ServiceError("redirect_refused", "Memory endpoint redirects are refused", 502) from error
            status = error.code
            body = error.read(MAX_BODY + 1)
        except (OSError, urllib.error.URLError) as error:
            raise ServiceError("unavailable", "Memory service is unavailable", 503) from error
        if len(body) > MAX_BODY:
            raise ServiceError("invalid_response", "Memory response exceeds the size limit", 502)
        try:
            payload = decode(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
                raise ValueError("Invalid envelope")
            if not payload["ok"]:
                raise ServiceError(payload["error"]["code"], payload["error"]["message"], status)
            return payload["result"]
        except (ValueError, KeyError, TypeError) as error:
            raise ServiceError("invalid_response", "Invalid memory response", 502) from error
