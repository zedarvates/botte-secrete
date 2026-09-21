"""Operator CLI for the shared-memory pilot (Python 3.10+, stdlib)."""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.memory_hub.shared_contract import PROJECT, SCHEMAS, decode, encode, openapi, validate
from skills.memory_hub.shared_http import AuthRegistry, MemoryHTTPClient, MemoryHTTPServer, read_token
from skills.memory_hub.shared_mcp import serve_stdio
from skills.memory_hub.shared_service import MemoryService, RIGHTS, ServiceError


def initialize(directory, project):
    validate(PROJECT, project)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    principals = []
    for actor, rights in (("worker", ["read", "write", "forget"]), ("operator", sorted(RIGHTS))):
        token_path = root / f"{actor}.secret"
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(48) + "\n")
        principals.append({"actor_id": actor, "projects": [project], "rights": rights,
                           "token_file": token_path.name})
    (root / "auth.json").write_text(encode({"schema": "botte.memory-auth/v1",
                                           "principals": principals}).decode("utf-8"), encoding="utf-8")
    return {"directory": str(root), "project_id": project,
            "operator_token_for_trusted_ingress_only": True, "started": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--directory", required=True)
    init.add_argument("--project", required=True)
    server = commands.add_parser("serve")
    server.add_argument("--directory", required=True)
    server.add_argument("--port", type=int, default=8766)
    for command in ("mcp", "call"):
        child = commands.add_parser(command)
        child.add_argument("--url", default="http://127.0.0.1:8766")
        child.add_argument("--token-file", required=True)
        if command == "call":
            child.add_argument("operation", choices=SCHEMAS)
            child.add_argument("--input", help="UTF-8 JSON file; stdin when omitted")
    commands.add_parser("schema")
    args = parser.parse_args(argv)
    force_utf8()
    try:
        if args.command == "init":
            result = initialize(args.directory, args.project)
        elif args.command == "schema":
            result = openapi()
        elif args.command == "serve":
            root = Path(args.directory)
            auth = AuthRegistry.load(root / "auth.json")
            with MemoryHTTPServer(("127.0.0.1", args.port), MemoryService(root / "data"), auth) as server:
                print(f"Botte memory pilot listening on loopback port {server.server_port}", file=sys.stderr)
                server.serve_forever()
            return 0
        else:
            client = MemoryHTTPClient(args.url, read_token(args.token_file))
            if args.command == "mcp":
                serve_stdio(client)
                return 0
            raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
            result = client.call(args.operation, decode(raw))
        print(encode(result).decode("utf-8"))
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, ServiceError) as error:
        print(encode({"error": getattr(error, "code", "configuration"),
                      "message": str(error)}).decode("utf-8"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
