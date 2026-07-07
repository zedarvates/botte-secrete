"""Agent wrappers for botte proxy — wrap/unwrap CLI tools.

Each agent has a wrapper that knows:
1. Which environment variables to set to route traffic through the proxy
2. How to launch the agent with those variables
3. How to detect if it's already wrapped

Supported agents:
- claude: Claude Code CLI
- codex: OpenAI Codex CLI
- openai: Any OpenAI-compatible agent (generic)
- ollama: Local Ollama (reverse proxy)
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Wrapper state ──────────────────────────────────────────────

BOTTE_WRAP_DIR = Path.home() / ".botte" / "wraps"
BOTTE_WRAP_STATE = BOTTE_WRAP_DIR / "state.json"


@dataclass
class WrapperState:
    """Persistent state for wrapped agents."""
    wrapped_agents: dict[str, dict] = field(default_factory=dict)
    proxy_port: int = 8787
    proxy_pid: Optional[int] = None

    def save(self):
        import json
        BOTTE_WRAP_DIR.mkdir(parents=True, exist_ok=True)
        BOTTE_WRAP_STATE.write_text(json.dumps({
            "wrapped_agents": self.wrapped_agents,
            "proxy_port": self.proxy_port,
            "proxy_pid": self.proxy_pid,
        }))

    @classmethod
    def load(cls) -> "WrapperState":
        import json
        if BOTTE_WRAP_STATE.exists():
            try:
                data = json.loads(BOTTE_WRAP_STATE.read_text())
                return cls(
                    wrapped_agents=data.get("wrapped_agents", {}),
                    proxy_port=data.get("proxy_port", 8787),
                    proxy_pid=data.get("proxy_pid"),
                )
            except (json.JSONDecodeError, KeyError):
                pass
        return cls()


@dataclass
class WrapResult:
    """Result of a wrap operation."""
    success: bool
    agent: str
    proxy_port: int
    proxy_url: str
    env_vars: dict[str, str] = field(default_factory=dict)
    message: str = ""


# ── Known agents ───────────────────────────────────────────────

AGENTS = {
    "claude": {
        "name": "Claude Code CLI",
        "binary": "claude",
        "pip_package": "claude-code",
        "env": lambda port, api_key: {
            "ANTHROPIC_BASE_URL": f"http://localhost:{port}",
            "HEADROOM": "botte-secrete",
        },
        "check_wrapped": lambda env: "ANTHROPIC_BASE_URL" in env and "localhost" in env.get("ANTHROPIC_BASE_URL", ""),
    },
    "codex": {
        "name": "OpenAI Codex CLI",
        "binary": "codex",
        "pip_package": "codex-cli",
        "env": lambda port, api_key: {
            "OPENAI_BASE_URL": f"http://localhost:{port}/v1",
            "CODEX_BASE_URL": f"http://localhost:{port}/v1",
        },
        "check_wrapped": lambda env: "OPENAI_BASE_URL" in env and "localhost" in env.get("OPENAI_BASE_URL", ""),
    },
    "aider": {
        "name": "Aider",
        "binary": "aider",
        "pip_package": "aider-chat",
        "env": lambda port, api_key: {
            "OPENAI_API_BASE": f"http://localhost:{port}/v1",
            "AIDER_OPENAI_API_BASE": f"http://localhost:{port}/v1",
        },
        "check_wrapped": lambda env: "OPENAI_API_BASE" in env and "localhost" in env.get("OPENAI_API_BASE", ""),
    },
    "opencode": {
        "name": "OpenCode CLI",
        "binary": "opencode",
        "pip_package": "opencode-cli",
        "env": lambda port, api_key: {
            "OPENAI_BASE_URL": f"http://localhost:{port}/v1",
        },
        "check_wrapped": lambda env: "OPENAI_BASE_URL" in env and "localhost" in env.get("OPENAI_BASE_URL", ""),
    },
    "openai": {
        "name": "Generic OpenAI-compatible client",
        "binary": None,
        "pip_package": None,
        "env": lambda port, api_key: {
            "OPENAI_BASE_URL": f"http://localhost:{port}/v1",
            "OPENAI_API_BASE": f"http://localhost:{port}/v1",
        },
        "check_wrapped": lambda env: "OPENAI_BASE_URL" in env and "localhost" in env.get("OPENAI_BASE_URL", ""),
    },
}


def find_binary(name: str) -> Optional[str]:
    """Find a binary in PATH."""
    return shutil.which(name)


def is_agent_installed(name: str) -> bool:
    """Check if an agent binary is available."""
    info = AGENTS.get(name)
    if not info:
        return False
    binary = info["binary"]
    if binary and find_binary(binary):
        return True
    return False


def list_available_agents() -> list[str]:
    """List agents that are installed and available."""
    return [name for name in AGENTS if is_agent_installed(name)]


# ── Wrapper implementation ─────────────────────────────────────


def start_proxy(port: int = 8787, target: Optional[str] = None) -> Optional[int]:
    """Start the botte proxy in the background.

    Returns PID if proxy started successfully, None otherwise.
    Uses subprocess with nohup to keep it running.
    """
    import socket

    # Check if port is already in use
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    if result == 0:
        print(f"  ℹ️  Proxy already running on port {port}")
        # Try to find PID
        try:
            pid = int(subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}"], stderr=subprocess.DEVNULL
            ).decode().strip().split("\n")[0])
            return pid
        except (subprocess.CalledProcessError, ValueError, IndexError):
            return None

    # Start proxy
    proxy_module = "skills.botte_proxy.cli"
    proxy_args = ["proxy", "--port", str(port)]
    if target:
        proxy_args.extend(["--target", target])

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", proxy_module] + proxy_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        import time
        time.sleep(1)  # Give it time to start

        # Verify it's running
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            print(f"  🧦 Proxy started on port {port} (PID {proc.pid})")
            return proc.pid
        else:
            print(f"  ❌ Proxy failed to start on port {port}")
            return None
    except Exception as e:
        print(f"  ❌ Failed to start proxy: {e}")
        return None


def wrap_agent(
    agent_name: str,
    proxy_port: int = 8787,
    target: Optional[str] = None,
    api_key: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
) -> WrapResult:
    """Wrap an agent to route through the botte proxy.

    Steps:
    1. Start the proxy if not already running
    2. Generate environment variables for the agent
    3. Save wrapper state
    4. Print instructions or launch the agent
    """
    agent_info = AGENTS.get(agent_name)
    if not agent_info:
        return WrapResult(False, agent_name, proxy_port, message=f"Unknown agent: {agent_name}")

    binary = agent_info["binary"]
    if binary and not find_binary(binary):
        return WrapResult(False, agent_name, proxy_port, proxy_url="",
                          message=f"Agent '{agent_name}' not found in PATH. Install it first.")

    # Start proxy
    pid = start_proxy(proxy_port, target)
    if pid is None and not _is_port_open(proxy_port):
        return WrapResult(False, agent_name, proxy_port, proxy_url="",
                          message=f"Failed to start proxy on port {proxy_port}")

    # Generate env vars
    env_fn = agent_info["env"]
    env_vars = env_fn(proxy_port, api_key)

    # Save state
    state = WrapperState.load()
    state.wrapped_agents[agent_name] = {
        "env_vars": env_vars,
        "proxy_port": proxy_port,
        "timestamp": __import__("time").time(),
    }
    state.proxy_port = proxy_port
    state.proxy_pid = pid
    state.save()

    proxy_url = f"http://localhost:{proxy_port}"

    # Print instructions
    print(f"\n🧦 Botte Secrète — Wrapping {agent_info['name']}")
    print(f"   Proxy: {proxy_url}")
    print(f"   Agent: {binary or agent_name}")
    for key, val in env_vars.items():
        print(f"   Env:   {key}={val}")
    print()

    if binary:
        cmd_parts = [binary]
        if extra_args:
            cmd_parts.extend(extra_args)
        cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)

        print(f"  Run with compression:")
        env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env_vars.items())
        print(f"    {env_prefix} {cmd_str}")
        print()
        print(f"  Or export env first:")
        for key, val in env_vars.items():
            print(f"    export {key}={shlex.quote(val)}")
        print(f"    {cmd_str}")
    else:
        print(f"  Set these environment variables to route through proxy:")
        for key, val in env_vars.items():
            print(f"    export {key}={shlex.quote(val)}")

    return WrapResult(True, agent_name, proxy_port, proxy_url=proxy_url,
                      env_vars=env_vars,
                      message=f"Agent '{agent_name}' wrapped. Proxy on port {proxy_port}.")


def unwrap_agent(agent_name: str) -> WrapResult:
    """Unwrap an agent — removes wrapper state."""
    state = WrapperState.load()

    if agent_name not in state.wrapped_agents:
        return WrapResult(False, agent_name, state.proxy_port, proxy_url="",
                          message=f"Agent '{agent_name}' is not wrapped.")

    # Save env vars before deleting
    agent_data = dict(state.wrapped_agents.get(agent_name, {}))
    env_vars = agent_data.get("env_vars", {})
    del state.wrapped_agents[agent_name]
    state.save()

    # Also create an unwrapper script
    agent_info = AGENTS.get(agent_name, {})
    print(f"\n🧦 Botte Secrète — Unwrapping {agent_info.get('name', agent_name)}")
    if env_vars:
        print(f"   Remove these environment variables:")
        for key in env_vars:
            print(f"    unset {key}")

    # If no agents left and proxy was started by us, suggest stopping it
    if not state.wrapped_agents and state.proxy_pid:
        print(f"   Stop proxy: kill {state.proxy_pid}")

    return WrapResult(True, agent_name, state.proxy_port, proxy_url="",
                      message=f"Agent '{agent_name}' unwrapped.")


def list_wrapped() -> list[dict]:
    """List all wrapped agents with their state."""
    state = WrapperState.load()
    result = []
    for agent, data in state.wrapped_agents.items():
        info = AGENTS.get(agent, {})
        result.append({
            "agent": agent,
            "name": info.get("name", agent),
            "env_vars": data.get("env_vars", {}),
            "proxy_port": data.get("proxy_port", state.proxy_port),
            "wrapped_since": __import__("time").ctime(data.get("timestamp", 0)),
        })
    return result


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is open."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()
