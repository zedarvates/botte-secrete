"""Install Botte Secrète MCP entries without overwriting existing tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SUPPORTED_TOOLS = ("claude", "cursor", "opencode", "codex", "antigravity", "hermes", "openclaw")


def _server(project: Path, botte_root: Path) -> dict[str, Any]:
    return {"command": sys.executable, "args": ["-m", "skills.llm_mcp.server"],
            "cwd": str(botte_root), "env": {"BOTTE_PROJECT_ROOT": str(project)}}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        raise ValueError(f"invalid JSON configuration: {path}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _json_install(path: Path, key: str, server: dict[str, Any]) -> str:
    config = _read_json(path)
    servers = config.setdefault(key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{key} must be an object in {path}")
    action = "updated" if "botte-llm" in servers else "added"
    servers["botte-llm"] = {"type": "local", **server} if key == "mcp" and path.name == "opencode.json" else server
    _write_json(path, config)
    return action


def _codex_install(path: Path, server: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = '[mcp_servers."botte-llm"]'
    block = f'{marker}\ncommand = {json.dumps(server["command"])}\nargs = ["-m", "skills.llm_mcp.server"]\ncwd = {json.dumps(server["cwd"])}\n'
    if marker in text:
        head, _, tail = text.partition(marker)
        next_section = tail.find("\n[")
        text = head + block + (tail[next_section + 1:] if next_section >= 0 else "")
        action = "updated"
    else:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + block
        action = "added"
    path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    return action


def _hermes_install(path: Path, server: dict[str, Any]) -> str:
    """Append the documented Hermes YAML MCP block without requiring PyYAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if "name: botte-llm" in text:
        return "updated"
    block = ("\n# Botte Secrète MCP\nmcp_servers:\n  - name: botte-llm\n"
             "    transport: stdio\n    command: " + json.dumps(server["command"]) +
             "\n    args: [\"-m\", \"skills.llm_mcp.server\"]\n"
             "    cwd: " + json.dumps(server["cwd"]) + "\n")
    path.write_text(text.rstrip() + block, encoding="utf-8")
    return "added"


def _openclaw_install(path: Path, server: dict[str, Any]) -> str:
    config = _read_json(path)
    servers = config.setdefault("mcp", {}).setdefault("servers", [])
    if not isinstance(servers, list):
        raise ValueError(f"mcp.servers must be an array in {path}")
    entry = {"name": "botte-llm", "enabled": True, "transport": "stdio",
             "command": server["command"], "args": server["args"], "cwd": server["cwd"]}
    found = next((item for item in servers if isinstance(item, dict) and item.get("name") == "botte-llm"), None)
    action = "updated" if found is not None else "added"
    if found is None:
        servers.append(entry)
    else:
        found.update(entry)
    _write_json(path, config)
    return action


def install_plugins(project: str | Path, *, tools: tuple[str, ...] = SUPPORTED_TOOLS,
                    botte_root: str | Path | None = None) -> dict[str, Any]:
    project_path = Path(project).resolve()
    if not project_path.is_dir():
        raise ValueError(f"project does not exist: {project_path}")
    root = Path(botte_root or Path(__file__).resolve().parents[2]).resolve()
    unknown = set(tools) - set(SUPPORTED_TOOLS)
    if unknown:
        raise ValueError(f"unsupported tools: {', '.join(sorted(unknown))}")
    server = _server(project_path, root)
    results: dict[str, str] = {}
    for tool in tools:
        if tool == "claude":
            results[tool] = _json_install(project_path / ".mcp.json", "mcpServers", server)
        elif tool == "cursor":
            results[tool] = _json_install(project_path / ".cursor" / "mcp.json", "mcpServers", server)
        elif tool == "opencode":
            results[tool] = _json_install(project_path / "opencode.json", "mcp", server)
        elif tool == "codex":
            results[tool] = _codex_install(project_path / ".codex" / "config.toml", server)
        elif tool == "antigravity":
            results[tool] = _json_install(project_path / ".gemini" / "antigravity" / "mcp_config.json", "mcpServers", server)
        elif tool == "hermes":
            results[tool] = _hermes_install(project_path / ".hermes" / "config.yaml", server)
        elif tool == "openclaw":
            results[tool] = _openclaw_install(project_path / ".openclaw" / "openclaw.json", server)
    return {"project": str(project_path), "botte_root": str(root), "tools": results}
