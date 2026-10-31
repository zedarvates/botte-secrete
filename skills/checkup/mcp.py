"""Static, project-scoped MCP declarations, without launching configured code.

A declaration or an executable file is not an MCP handshake. User/global and
installed-plugin configuration is deliberately outside this file inspection.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from urllib.parse import urlsplit

try:
    import tomllib
except ImportError:  # Python 3.10: do not invent a partial TOML parser.
    tomllib = None


_MAX_CONFIG_BYTES = 128 * 1024
_SOURCES = (
    (".mcp.json", "json", ("mcpServers",)),
    (".cursor/mcp.json", "json", ("mcpServers",)),
    ("opencode.json", "json", ("mcp",)),
    (".codex/config.toml", "toml", ("mcp_servers",)),
    (".gemini/antigravity/mcp_config.json", "json", ("mcpServers",)),
    (".hermes/config.yaml", "yaml", ()),
    (".openclaw/openclaw.json", "json", ("mcp", "servers")),
)


def _launcher(entry: dict, command: str) -> dict:
    # Avoid treating one process's resolution as the host's launch environment.
    if "cwd" in entry or "env" in entry or "${" in command or "%" in command:
        return {"status": "not_checked", "basis": "host_launch_environment_unknown"}
    try:
        path = Path(command)
        if path.is_absolute():
            found = path.is_file() and os.access(path, os.X_OK)
            basis = "executable_file_in_current_filesystem"
        elif path.name != command or "\\" in command:
            return {"status": "not_checked", "basis": "relative_launch_path"}
        else:
            found = shutil.which(command) is not None
            basis = "current_process_PATH"
    except (OSError, ValueError):
        return {"status": "not_checked", "basis": "launcher_inspection_failed"}
    return {"status": "found" if found else "not_found", "basis": basis}


def _entry_summary(entry: object) -> dict:
    if not isinstance(entry, dict) or not entry:
        return {"status": "invalid", "reason": "entry_must_be_nonempty_object"}
    if any(key in entry and not isinstance(entry[key], bool) for key in ("disabled", "enabled")):
        return {"status": "invalid", "reason": "enabled_disabled_must_be_boolean"}
    if entry.get("disabled") is True or entry.get("enabled") is False:
        return {"status": "disabled", "reason": "disabled_in_declaration"}
    if "cwd" in entry and (not isinstance(entry["cwd"], str) or not entry["cwd"] or "\x00" in entry["cwd"]):
        return {"status": "invalid", "reason": "cwd_must_be_nonempty_string"}
    if "env" in entry and (not isinstance(entry["env"], dict)
                           or not all(isinstance(k, str) and isinstance(v, str)
                                      and "\x00" not in k and "\x00" not in v
                                      for k, v in entry["env"].items())):
        return {"status": "invalid", "reason": "env_must_be_string_object"}
    if "command" in entry:
        if "url" in entry:
            return {"status": "invalid", "reason": "ambiguous_command_and_url"}
        if entry.get("type", "stdio") not in ("stdio", "local") or entry.get("transport", "stdio") != "stdio":
            return {"status": "unsupported", "reason": "unsupported_command_transport"}
        command = entry["command"]
        # OpenCode also permits a command array. Inspect only the launcher.
        if isinstance(command, list) and command and all(isinstance(x, str) and "\x00" not in x for x in command):
            command = command[0]
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            return {"status": "invalid", "reason": "command_must_be_nonempty_string_or_array"}
        if "args" in entry and (not isinstance(entry["args"], list)
                                or not all(isinstance(x, str) and "\x00" not in x for x in entry["args"])):
            return {"status": "invalid", "reason": "args_must_be_string_array"}
        return {"status": "configured", "transport": "stdio", "launcher": _launcher(entry, command)}
    url = entry.get("url")
    if isinstance(url, str):
        if entry.get("type", "http") not in ("http", "sse", "streamable-http", "remote") or entry.get("transport", "http") not in ("http", "sse", "streamable-http"):
            return {"status": "unsupported", "reason": "unsupported_url_transport"}
        try:
            parsed = urlsplit(url)
            _ = parsed.port  # Validate a supplied port without resolving DNS.
            if parsed.scheme in ("http", "https") and parsed.hostname and "\x00" not in url:
                return {"status": "configured", "transport": "http",
                        "launcher": {"status": "not_applicable", "basis": "remote_declaration"}}
        except ValueError:
            pass
    return {"status": "invalid", "reason": "missing_supported_command_or_url"}


def _inspect_source(project: Path, relative: str, kind: str, keys: tuple) -> dict | None:
    path = project / relative
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            return {"path": relative, "status": "unreadable", "reason": "not_regular_file"}
        # read() keeps an oversized file from consuming unbounded memory.
        with path.open("rb") as stream:
            raw = stream.read(_MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        return {"path": relative, "status": "unreadable", "reason": "read_failed"}
    result = {"path": relative}
    if len(raw) > _MAX_CONFIG_BYTES:
        return {**result, "status": "invalid", "reason": "configuration_size_limit"}
    if kind == "yaml" or (kind == "toml" and tomllib is None):
        return {**result, "status": "unsupported", "reason": "parser_unavailable"}
    try:
        text = raw.decode("utf-8")
        doc = json.loads(text) if kind == "json" else tomllib.loads(text)
    except (ValueError, RecursionError):
        return {**result, "status": "invalid", "reason": "configuration_parse_failed"}
    if not isinstance(doc, dict):
        return {**result, "status": "invalid", "reason": "configuration_must_be_object"}
    servers = doc
    for key in keys:
        if not isinstance(servers, dict):
            return {**result, "status": "invalid", "reason": "invalid_server_container"}
        if key not in servers:
            return {**result, "status": "missing", "reason": "no_botte_declaration"}
        servers = servers[key]
    if relative == ".openclaw/openclaw.json":
        if not isinstance(servers, list):
            return {**result, "status": "invalid", "reason": "invalid_server_container"}
        entries = [x for x in servers if isinstance(x, dict) and x.get("name") == "botte-llm"]
        if len(entries) > 1:
            return {**result, "status": "invalid", "reason": "duplicate_botte_declaration"}
        entry = entries[0] if entries else None
        present = bool(entries)
    else:
        if not isinstance(servers, dict):
            return {**result, "status": "invalid", "reason": "invalid_server_container"}
        present = "botte-llm" in servers
        entry = servers.get("botte-llm")
    if not present:
        return {**result, "status": "missing", "reason": "no_botte_declaration"}
    return {**result, **_entry_summary(entry)}


def inspect_mcp(project: Path) -> dict:
    """Report declarations and launcher hints; runtime/reachability stay unknown."""
    sources = [r for relative, kind, keys in _SOURCES
               if (r := _inspect_source(Path(project), relative, kind, keys)) is not None]
    statuses = {r["status"] for r in sources}
    status = next((x for x in ("configured", "invalid", "unreadable", "unsupported", "disabled")
                   if x in statuses), "missing")
    return {"status": status, "applicable": True,
            "scope": "project_files_only", "runtime": "not_checked", "reachability": "not_checked",
            "sources": sources,
            "not_inspected": ["user_global_configuration", "installed_plugin_configuration"],
            "inspected_paths": [x[0] for x in _SOURCES]}
