"""Reference machine-agent — receives delegated tasks safely.

Deploy this (or wire Hermes to behave like it) on each homelab machine so the
cluster can hand it work. Security-first by design:

  * **Whitelist only.** It runs *named* actions from ACTIONS, never arbitrary
    shell from the network. Default actions are READ-ONLY (status/disk/backends).
  * **Loopback by default.** Binds 127.0.0.1 unless you pass a host; a non-loopback
    bind *requires* a shared token (BOTTE_AGENT_TOKEN).
  * **No privileged maintenance enabled by default.** Restart/update handlers are
    intentionally absent — add them deliberately, gated, when you scope the policy.

    python -m skills.cluster.agent serve [--host H] [--port 8799] [--token T]

Pure stdlib (http.server). The cluster's `delegate(host, task)` POSTs
{"task": "<action>"} (or {"task": {"action": .., "args": {..}}}) to /task.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


# ── whitelisted, read-only actions ──────────────────────────────────────────

def _machine_status(_args: dict) -> dict:
    try:
        from skills.llm_backends.audit import profile_hardware
        hw = profile_hardware().to_dict()
    except Exception:
        hw = {"os": f"{platform.system()} {platform.release()}",
              "cpu_cores": os.cpu_count()}
    load = None
    if hasattr(os, "getloadavg"):
        try:
            load = os.getloadavg()
        except OSError:
            load = None
    return {"hostname": platform.node(), "hardware": hw, "loadavg": load}


def _disk(_args: dict) -> dict:
    out = {}
    root = "C:\\" if platform.system() == "Windows" else "/"
    try:
        u = shutil.disk_usage(root)
        out[root] = {"total_gb": round(u.total / 1024**3, 1),
                     "free_gb": round(u.free / 1024**3, 1),
                     "used_pct": round(u.used / u.total * 100)}
    except OSError as e:
        out["error"] = str(e)
    return out


def _local_backends(_args: dict) -> dict:
    try:
        from skills.llm_backends.discovery import scan_host
        bs = scan_host("127.0.0.1", timeout=1.0)
        return {"backends": [f"{b.label}:{b.port}" for b in bs]}
    except Exception as e:
        return {"error": str(e)}


def _ping(_args: dict) -> dict:
    return {"ok": True, "host": platform.node()}


# Read-only only. Privileged maintenance comes from operator-defined named
# commands (see _COMMANDS), never arbitrary shell.
ACTIONS: dict[str, Callable[[dict], dict]] = {
    "ping": _ping,
    "machine_status": _machine_status,
    "disk": _disk,
    "local_backends": _local_backends,
}

# Operator-approved maintenance commands: {name: {"cmd": [argv...], "desc": str}}.
# Populated only when the operator passes a commands file at startup. The remote
# caller can ONLY trigger these by name (like a restricted sudoers) and must
# include "confirm": true. Empty by default → no privileged actions at all.
_COMMANDS: dict[str, dict] = {}
_CMD_TIMEOUT = 120


def load_commands(path) -> dict:
    """Load the operator's maintenance command whitelist from a JSON file."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, spec in (doc.get("commands", doc) or {}).items():
        if isinstance(spec, dict) and isinstance(spec.get("cmd"), list):
            out[name] = {"cmd": [str(a) for a in spec["cmd"]],
                         "desc": str(spec.get("desc", ""))}
    return out


def _run_named(name: str, confirm: bool) -> dict:
    """Run an operator-approved maintenance command (by name only, confirm-gated)."""
    import subprocess
    spec = _COMMANDS.get(name)
    if not spec:
        return {"ok": False, "error": f"maintenance command not permitted: {name!r}",
                "allowed": sorted(_COMMANDS)}
    if confirm is not True:
        return {"ok": False, "error": "confirmation required: pass confirm=true",
                "command": name, "desc": spec["desc"], "will_run": spec["cmd"]}
    try:
        proc = subprocess.run(spec["cmd"], capture_output=True, text=True,
                              timeout=_CMD_TIMEOUT)
        return {"ok": proc.returncode == 0, "command": name, "exit": proc.returncode,
                "output": ((proc.stdout or "") + (proc.stderr or ""))[-2000:]}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "command": name, "error": str(e)}


def handle_task(payload: dict) -> dict:
    """Dispatch a delegated task. Read-only actions always; maintenance only via
    operator-approved named commands with confirm=true. Never arbitrary shell."""
    task = payload.get("task", payload)
    if isinstance(task, str):
        action, args = task, {}
    elif isinstance(task, dict):
        action, args = task.get("action", ""), task.get("args", {})
    else:
        return {"ok": False, "error": "bad task"}
    args = args or {}

    if action == "list_commands":  # read-only: what maintenance is permitted here
        return {"ok": True, "action": action,
                "result": {n: s["desc"] for n, s in _COMMANDS.items()}}
    if action == "run":            # operator-approved maintenance, confirm-gated
        return {"action": "run", **_run_named(args.get("name", ""),
                                              args.get("confirm", False))}

    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"action not allowed: {action!r}",
                "allowed": sorted(ACTIONS) + ["run", "list_commands"]}
    try:
        return {"ok": True, "action": action, "result": fn(args)}
    except Exception as e:
        return {"ok": False, "action": action, "error": str(e)}


# ── HTTP receiver ─────────────────────────────────────────────────────────────

def _make_handler(token: str):
    class _H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if token and self.headers.get("X-Botte-Token") != token:
                return self._send(401, {"ok": False, "error": "bad token"})
            if self.path != "/task":
                return self._send(404, {"ok": False, "error": "use POST /task"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"ok": False, "error": "bad JSON"})
            self._send(200, handle_task(payload))

        def log_message(self, *a):  # quiet
            pass

    return _H


def serve(host: str = "127.0.0.1", port: int = 8799, token: str = "",
          commands: str = "") -> int:
    global _COMMANDS
    token = token or os.environ.get("BOTTE_AGENT_TOKEN", "")
    commands = commands or os.environ.get("BOTTE_AGENT_COMMANDS", "")
    if commands:
        _COMMANDS = load_commands(commands)
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not loopback and not token:
        print("REFUSED: non-loopback bind requires a token (BOTTE_AGENT_TOKEN or --token).")
        return 2
    if _COMMANDS and not loopback and not token:
        print("REFUSED: maintenance commands enabled on a non-loopback bind without a token.")
        return 2
    srv = ThreadingHTTPServer((host, port), _make_handler(token))
    print(f"botte machine-agent on http://{host}:{port}/task "
          f"({'token-gated' if token else 'loopback, no token'}); "
          f"read-only: {', '.join(sorted(ACTIONS))}; "
          f"maintenance (confirm-gated): {', '.join(sorted(_COMMANDS)) or 'none'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="botte-agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the receiver")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8799)
    s.add_argument("--token", default="")
    s.add_argument("--commands", default="",
                   help="JSON file of operator-approved maintenance commands "
                        "(enables confirm-gated `run` of named commands)")
    args = p.parse_args(argv)
    return serve(args.host, args.port, args.token, args.commands)


if __name__ == "__main__":
    raise SystemExit(main())
