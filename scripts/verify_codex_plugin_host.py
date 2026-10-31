#!/usr/bin/env python3
"""Qualify a local plugin through a real Codex CLI/app-server, without an LLM turn.

Run only in a disposable, initially empty Codex profile. This script never
changes HOME or CODEX_HOME. CI's fresh account or a filesystem namespace must
provide isolation; an existing config/auth/cache makes this probe fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

MAX_LINE = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_REPORT = 64 * 1024
TIMEOUT = 45
ALLOWED_METHODS = {
    "initialize", "plugin/list", "plugin/read", "skills/list", "thread/start",
    "mcpServerStatus/list", "mcpServer/tool/call",
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(argv, *, cwd, env, timeout=60):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    require(result.returncode == 0, "command failed: " + Path(argv[0]).name + " " +
            " ".join(argv[1:4]) + "; " + result.stderr[-1500:])
    require(len(result.stdout.encode("utf-8")) <= MAX_LINE, "command output exceeds bound")
    return result.stdout


class AppServer:
    """Bounded NDJSON transport; the allowlist excludes every model-turn method."""

    def __init__(self, codex, cwd, env):
        self.codex, self.cwd, self.env = codex, cwd, env
        self.sequence = self.sent = self.received = 0
        self.lines = queue.Queue(maxsize=256)
        self.stderr = bytearray()
        self.methods = []

    def __enter__(self):
        self.process = subprocess.Popen([self.codex, "app-server", "--stdio"],
                                        cwd=self.cwd, env=self.env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def read_stdout():
            while True:
                raw = self.process.stdout.readline(MAX_LINE + 1)
                try:
                    self.lines.put(raw or None, timeout=TIMEOUT)
                except queue.Full:
                    return
                if not raw or len(raw) > MAX_LINE:
                    return

        def read_stderr():
            while True:
                raw = self.process.stderr.read(1024)
                if not raw:
                    return
                self.stderr.extend(raw[:max(0, 4096 - len(self.stderr))])

        self.reader = threading.Thread(target=read_stdout, daemon=True)
        self.errors = threading.Thread(target=read_stderr, daemon=True)
        self.reader.start()
        self.errors.start()
        try:
            self.rpc("initialize", {"clientInfo": {"name": "botte-plugin-qualification", "version": "1"},
                                    "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized"})
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def send(self, value):
        raw = (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        self.sent += len(raw)
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def rpc(self, method, params=None):
        require(method in ALLOWED_METHODS, "unapproved app-server method: " + method)
        self.methods.append(method)
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "app-server response timeout: " + method)
            try:
                raw = self.lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise AssertionError("app-server response timeout: " + method) from exc
            require(raw is not None, "app-server exited before response: " + method)
            require(len(raw) <= MAX_LINE, "app-server line exceeds bound")
            self.received += len(raw)
            require(self.received <= MAX_TOTAL, "app-server output exceeds bound")
            message = json.loads(raw)
            if "method" in message:
                # No approval, elicitation, execution or authentication is delegated
                # to a server-initiated request during this qualification.
                if "id" in message:
                    self.send({"id": message["id"], "error": {"code": -32601,
                              "message": "Host qualification declines server requests"}})
                continue
            require(message.get("id") == request_id, "unexpected response identity")
            require("error" not in message, "app-server RPC failed: " + method + "; " +
                    json.dumps(message.get("error"), ensure_ascii=True)[:1500])
            return message["result"]

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.errors.join(timeout=1)
        return False


def load_callbacks(repo):
    spec = importlib.util.spec_from_file_location("candidate_workflow_callbacks",
                                                 repo / "scripts/verify_parcimonia_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HostedSession:
    """Adapt the authored workflow checks to calls made through Codex itself."""

    def __init__(self, host, thread_id, server, cwd):
        self.host, self.thread_id, self.server, self.cwd = host, thread_id, server, cwd

    def rpc(self, method, params=None):
        require(method == "tools/list", "unsupported MCP adapter operation")
        return {"tools": list(self.server["tools"].values())}

    def tool(self, name, arguments, *, expected_error=False):
        require(name in {"find_tool", "assess_task", "compute_statistics",
                         "find_file_duplicates", "check_local_links"},
                "unapproved qualification tool: " + name)
        result = self.host.rpc("mcpServer/tool/call", {"threadId": self.thread_id,
            "server": self.server["name"], "tool": name, "arguments": arguments})
        require(bool(result.get("isError")) == expected_error, "unexpected hosted tool error: " + name)
        if expected_error:
            return None
        content = result.get("content", [])
        require(len(content) == 1 and content[0].get("type") == "text", "unexpected hosted MCP content")
        return json.loads(content[0]["text"])

    def discover_and_assess(self, name, task, intent):
        tools = self.rpc("tools/list")["tools"]
        names = {item["name"] for item in tools}
        require("find_tool" in names and "assess_task" in names and name not in names,
                "plugin MCP lazy tool boundary differs")
        discovery = self.tool("find_tool", {"query": name})
        tool = next(item for item in discovery["matches"] if item["name"] == name)
        require("inputSchema" in tool, "hosted tool discovery lacks schema")
        assessment = self.tool("assess_task", {"task": task, "available_tools": [
            {"name": name, "description": tool["description"]}]})
        require(assessment["status"] == "proposed" and assessment["intent"] == intent,
                "hosted task assessment differs")
        require(assessment["candidate_tools"][0]["name"] == name,
                "hosted assessment selected wrong offered tool")
        require(assessment["boundaries"]["execution"] is False,
                "hosted assessment claims execution")


def plugin_metadata(host, repo, work, profile):
    listing = host.rpc("plugin/list", {"cwds": [str(repo)], "forceRefetch": False,
                                      "marketplaceKinds": ["local"]})
    require(not listing.get("marketplaceLoadErrors"), "marketplace discovery failed")
    market = next(m for m in listing["marketplaces"] if m["name"] == "botte-secrete-marketplace")
    summary = next(p for p in market["plugins"] if p["name"] == "botte-secrete")
    require(summary["installed"] and summary["enabled"], "plugin is not installed and enabled in host")
    detail = host.rpc("plugin/read", {"marketplacePath": market["path"],
                                      "pluginName": "botte-secrete"})["plugin"]
    require(detail["summary"]["id"] == summary["id"], "plugin detail identity differs")
    require("botte-llm" in detail["mcpServers"], "plugin MCP declaration is absent")
    skill_name = "botte-secrete:botte-secrete"
    plugin_skills = [s for s in detail["skills"] if s["name"] == skill_name and s["enabled"]]
    require(len(plugin_skills) == 1, "enabled plugin skill missing from host detail")
    skill_listing = host.rpc("skills/list", {"cwds": [str(work)], "forceReload": True})
    entries = [s for item in skill_listing["data"] for s in item["skills"]
               if s["name"] == skill_name and s.get("pluginId") == summary["id"] and s["enabled"]]
    require(len(entries) == 1, "skills/list does not expose the installed plugin-owned skill")
    cached = Path(entries[0]["path"]).resolve()
    require(inside(cached, profile / "plugins") and not inside(cached, repo),
            "host skill is not loaded from its installed cache")
    source_root = repo / "plugins/botte-secrete"
    source_skill = source_root / "skills/botte-secrete/SKILL.md"
    require(digest(cached) == digest(source_skill), "installed plugin skill differs from candidate")
    cache_root = cached.parents[2]
    hashes = {}
    for relative in (".codex-plugin/plugin.json", ".mcp.json", "skills/botte-secrete/SKILL.md"):
        require(digest(cache_root / relative) == digest(source_root / relative),
                "installed plugin file differs: " + relative)
        hashes[relative] = digest(cache_root / relative)
    return summary["id"], {"installed": True, "enabled": True, "plugin_id": summary["id"],
            "cache_copy_verified": True, "skill_plugin_origin_verified": True,
            "files_sha256": hashes}


def start_thread(host, work):
    result = host.rpc("thread/start", {"cwd": str(work), "ephemeral": True,
                                      "sandbox": "read-only", "approvalPolicy": "never"})
    return result["thread"]["id"]


def wait_server(host, thread_id, plugin_id, *, expected_unavailable=False):
    deadline = time.monotonic() + 35
    last = None
    while time.monotonic() < deadline:
        result = host.rpc("mcpServerStatus/list", {"threadId": thread_id, "limit": 100})
        require(not result.get("nextCursor"), "MCP status pagination is incomplete")
        matches = [item for item in result["data"] if item.get("pluginId") == plugin_id]
        require(len(matches) <= 1, "multiple MCP servers unexpectedly belong to plugin")
        if matches:
            last = matches[0]
            require("botte-llm" in last["name"], "unexpected plugin server name")
            if expected_unavailable and (last.get("runtimeStatus") == "failed" or last.get("toolsError")):
                require(not last["tools"], "unavailable MCP unexpectedly has cached tools")
                return last
            if not expected_unavailable and last.get("runtimeStatus") == "connected" and last["tools"]:
                require(not last.get("toolsError"), "connected plugin MCP has discovery error")
                require(last.get("serverInfo", {}).get("name") == "botte-llm", "wrong initialized MCP server")
                return last
            if not expected_unavailable and last.get("runtimeStatus") == "failed":
                raise AssertionError("plugin MCP failed: " + str(last.get("toolsError"))[:800])
        time.sleep(0.25)
    raise AssertionError("plugin MCP did not reach expected state: " + str({
        "name": last.get("name"), "runtimeStatus": last.get("runtimeStatus"),
        "toolsError": last.get("toolsError")} if last else None)[:1200])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runtime-python", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--negative-runtime", action="store_true")
    args = parser.parse_args(argv)
    began = time.perf_counter_ns()
    report = {"schema": "botte.codex-plugin-host/v1", "status": "failed",
              "source_commit": args.source_commit, "model_turns_started": 0,
              "automatic_skill_selection": "not_tested", "provider_tokens": None,
              "cost": None, "savings": None, "scenarios": [],
              "thread_sandbox": "read-only"}
    try:
        require(re.fullmatch(r"[0-9a-f]{40}", args.source_commit), "source commit must be a full SHA")
        repo, codex = args.repo.resolve(), args.codex.absolute()
        profile = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).absolute()
        require(not (profile / "config.toml").exists() and not (profile / "auth.json").exists()
                and not (profile / "plugins").exists(), "a disposable initially empty Codex profile is required")
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", BOTTE_MCP_LAZY_TOOLS="1")
        scripts = args.runtime_python.absolute().parent
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        runtime_command = shutil.which("botte-mcp", path=env["PATH"])
        require(runtime_command is not None and inside(runtime_command, scripts), "plugin command does not resolve to installed runtime")
        runtime_check = """import importlib.util,json,sys
from pathlib import Path
p=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('candidate',p/'scripts/verify_parcimonia_candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
r,_=m.installed_runtime(p);r['source_wheel_installed_sha256']=m.verify_wheel_modules(p,Path(sys.argv[2]));print(json.dumps(r))
"""
        report["runtime"] = json.loads(command([str(args.runtime_python), "-I", "-c", runtime_check,
                                                str(repo), str(args.wheel.resolve())], cwd=Path.cwd(), env=env))
        report["wheel_sha256"] = digest(args.wheel)
        report["codex_version"] = command([str(codex), "--version"], cwd=Path.cwd(), env=env).strip()
        command([str(codex), "plugin", "marketplace", "add", str(repo), "--json"], cwd=Path.cwd(), env=env)
        command([str(codex), "plugin", "add", "botte-secrete@botte-secrete-marketplace", "--json"], cwd=Path.cwd(), env=env)
        callbacks = load_callbacks(repo)
        with tempfile.TemporaryDirectory(prefix="botte-codex-host-") as directory:
            work = Path(directory)
            with AppServer(str(codex), work, env) as host:
                plugin_id, report["plugin"] = plugin_metadata(host, repo, work, profile)
                thread_id = start_thread(host, work)
                server = wait_server(host, thread_id, plugin_id)
                report["mcp"] = {"name": server["name"], "plugin_id": plugin_id,
                    "runtime_status": server["runtimeStatus"], "server_info": server["serverInfo"],
                    "tool_names": sorted(server["tools"])}
                adapter = HostedSession(host, thread_id, server, work)
                for name, verify in (("statistics", callbacks.statistics),
                                     ("file_duplicates", callbacks.duplicates), ("local_links", callbacks.links)):
                    started = time.perf_counter_ns()
                    observation = verify(adapter)
                    report["scenarios"].append({"name": name, "status": "passed",
                        "elapsed_ns": time.perf_counter_ns() - started, "observations": observation})
                report["host_transport"] = {"methods": sorted(set(host.methods)),
                    "input_utf8_bytes": host.sent, "output_utf8_bytes": host.received}
            if args.negative_runtime:
                negative_env = dict(env)
                negative_env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep)
                    if p and shutil.which("botte-mcp", path=p) is None)
                require(shutil.which("botte-mcp", path=negative_env["PATH"]) is None,
                        "negative witness still resolves a runtime command")
                with AppServer(str(codex), work, negative_env) as host:
                    thread_id = start_thread(host, work)
                    unavailable = wait_server(host, thread_id, plugin_id, expected_unavailable=True)
                    report["negative_runtime"] = {"status": "correctly_unavailable",
                                                  "runtime_status": unavailable.get("runtimeStatus"),
                                                  "tool_count": len(unavailable["tools"])}
            report["status"] = "passed"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
    report["elapsed_ns"] = time.perf_counter_ns() - began
    raw = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    require(len(raw.encode("utf-8")) <= MAX_REPORT, "host report exceeds 64 KiB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(raw, encoding="utf-8")
    print(json.dumps({"status": report["status"], "codex_version": report.get("codex_version"),
                      "scenarios_passed": len(report["scenarios"]), "error": report.get("error")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
