import json
from pathlib import Path

from skills.plugins.installer import install_plugins


def test_installer_preserves_existing_servers_and_writes_all_adapters(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"existing": {"command": "keep"}}}), encoding="utf-8")
    result = install_plugins(tmp_path)
    assert set(result["tools"]) == {"claude", "cursor", "opencode", "codex", "antigravity"}
    assert json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["existing"]["command"] == "keep"
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / "opencode.json").exists()
    assert '[mcp_servers."botte-llm"]' in (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert (tmp_path / ".gemini" / "antigravity" / "mcp_config.json").exists()


def test_installer_is_idempotent(tmp_path):
    first = install_plugins(tmp_path)
    second = install_plugins(tmp_path)
    assert set(first["tools"]) == set(second["tools"])
    assert all(action == "updated" for action in second["tools"].values())
