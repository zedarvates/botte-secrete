#!/usr/bin/env python3
"""Verify installed Parcimonia workflows through the plugin's real stdio command.

Run with the candidate wheel's isolated venv Python (-I), outside its checkout.
The report qualifies authored fixtures and descriptor wiring, not a Codex host
installation, held-out task accuracy or a baseline/candidate cost comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
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
import zipfile

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024
TIMEOUT_SECONDS = 20


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Session:
    """Small bounded NDJSON client; no in-process server handler shortcuts."""

    def __init__(self, command, cwd, *, launch_env=None):
        self.command, self.cwd = command, cwd
        self.launch_env = dict(launch_env or {})
        self.sent = self.received = self.sequence = 0
        self.lines = queue.Queue(maxsize=64)
        self.stderr = bytearray()

    def __enter__(self):
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "PYTHONHOME"}}
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        env.update(self.launch_env)
        env["PATH"] = str(Path(self.command[0]).parent) + os.pathsep + env.get("PATH", "")
        resolved = shutil.which("botte-mcp", path=env["PATH"])
        require(resolved is not None and Path(resolved).resolve() == Path(self.command[0]).resolve(),
                "plugin's bare command does not resolve to the verified venv executable")
        self.process = subprocess.Popen(self.command, cwd=self.cwd, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

        def stdout_reader():
            while True:
                line = self.process.stdout.readline(MAX_RESPONSE_BYTES + 1)
                if not line:
                    self.lines.put(None)
                    return
                self.lines.put(line)
                if len(line) > MAX_RESPONSE_BYTES:
                    return

        def stderr_reader():
            while True:
                block = self.process.stderr.read(1024)
                if not block:
                    return
                self.stderr.extend(block[:max(0, 4096 - len(self.stderr))])

        self.reader = threading.Thread(target=stdout_reader, daemon=True)
        self.errors = threading.Thread(target=stderr_reader, daemon=True)
        self.reader.start()
        self.errors.start()
        try:
            result = self.rpc("initialize", {"protocolVersion": "2024-11-05",
                              "capabilities": {}, "clientInfo": {"name": "parcimonia-candidate", "version": "1"}})
            require(result["serverInfo"]["name"] == "botte-llm", "wrong MCP server")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def send(self, request):
        raw = (json.dumps(request, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        self.sent += len(raw)
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def rpc(self, method, params=None):
        self.sequence += 1
        self.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params or {}})
        try:
            raw = self.lines.get(timeout=TIMEOUT_SECONDS)
        except queue.Empty as exc:
            raise AssertionError("MCP response timeout") from exc
        require(raw is not None, "MCP exited before its response")
        require(len(raw) <= MAX_RESPONSE_BYTES, "MCP response exceeds 1 MiB")
        self.received += len(raw)
        require(self.received <= 8 * MAX_RESPONSE_BYTES, "MCP session output exceeds 8 MiB")
        response = json.loads(raw)
        require(response.get("id") == self.sequence and response.get("jsonrpc") == "2.0", "MCP response identity mismatch")
        require("error" not in response, "MCP protocol error")
        return response["result"]

    def tool(self, name, arguments, *, expected_error=False):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        require(bool(result.get("isError")) == expected_error, "unexpected MCP tool error state: " + name)
        if expected_error:
            return None
        content = result["content"]
        require(len(content) == 1 and content[0]["type"] == "text", "unexpected MCP content")
        return json.loads(content[0]["text"])

    def discover_and_assess(self, name, task, intent):
        tools = self.rpc("tools/list")["tools"]
        offered = {item["name"]: item for item in tools}
        require("assess_task" in offered and name in offered, "specialized tool is absent from the native catalog")
        tool = offered[name]
        require("inputSchema" in tool, "advertised tool has no executable schema")
        assessment = self.tool("assess_task", {"task": task, "available_tools": [
            {"name": tool["name"], "description": tool["description"]}]})
        require(assessment["status"] == "proposed" and assessment["intent"] == intent, "task assessment did not propose expected workflow")
        require(assessment["candidate_tools"][0]["name"] == name, "wrong offered tool selected")
        require(assessment["boundaries"]["execution"] is False, "assessment unexpectedly claims execution")

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            if exc_type is None:
                raise AssertionError("MCP did not exit after stdin EOF")
            return False
        self.reader.join(timeout=1)
        self.errors.join(timeout=1)
        if exc_type is None:
            require(code == 0, "MCP process failed: " + self.stderr.decode("utf-8", errors="replace")[:2000])
        return False


def statistics(session):
    session.discover_and_assess("compute_statistics", "Compute statistics for these values", "statistics")
    report = session.tool("compute_statistics", {"values": [10, 20, 30, 40], "percentiles": [95]})
    require(report["results"]["mean"] == 25 and report["percentiles"][0]["value"] == 38.5, "statistics values differ")
    session.tool("compute_statistics", {"values": [True]}, expected_error=True)
    abstained = session.tool("assess_task", {"task": "Ne calcule pas les statistiques", "available_tools": []})
    require(abstained["status"] == "abstained" and not abstained["candidate_tools"], "negated task did not abstain")
    return {"mean": 25, "percentile_95": 38.5, "invalid_input_rejected": True, "negated_task_abstained": True}


def duplicates(session):
    session.discover_and_assess("find_file_duplicates", "Find duplicate files", "file_duplicates")
    root = Path(session.cwd) / "duplicate-fixtures"
    root.mkdir()
    content = b"candidate-identical-bytes"
    for name, data in {"a.bin": content, "b.bin": content, "different.bin": b"different"}.items():
        (root / name).write_bytes(data)
    hardlink = True
    try:
        os.link(root / "a.bin", root / "alias.bin")
    except OSError:
        hardlink = False
    before = {path.name: (sha256(path), path.stat().st_mtime_ns) for path in root.iterdir()}
    report = session.tool("find_file_duplicates", {"root": str(root)})
    require(report["status"] == "complete" and report["group_count"] == 1, "duplicate group differs")
    require(report["groups"][0]["match"] == "exact_bytes" and report["groups"][0]["file_count"] == 2, "duplicates were not independent byte-verified copies")
    require(report["summary"]["logical_duplicate_bytes"] == len(content), "wrong logical duplicate byte count")
    if hardlink:
        require(report["hardlink_group_count"] == 1, "hardlink aliases were not separated")
    partial = session.tool("find_file_duplicates", {"root": str(root), "max_total_bytes": 1})
    require(partial["status"] == "partial" and partial["scan_partial"], "bounded duplicate scan lost partial state")
    session.tool("find_file_duplicates", {"root": str(root), "delete": True}, expected_error=True)
    after = {path.name: (sha256(path), path.stat().st_mtime_ns) for path in root.iterdir()}
    require(before == after, "duplicate fixtures were modified")
    return {"groups": 1, "independent_copies": 2, "hardlink_check": "passed" if hardlink else "unavailable",
            "content_and_mtime_preserved": True, "partial_scan_retained": True, "destructive_argument_rejected": True}


def links(session):
    session.discover_and_assess("check_local_links", "Check local Markdown links", "local_links")
    arguments = {"documents": [{"path": "README.md", "text": "[present](docs/guide.md)\n[missing](docs/lost.md)"}],
                 "available_paths": ["README.md", "docs/guide.md"], "inventory_complete": True}
    report = session.tool("check_local_links", arguments)
    require(report["status"] == "complete" and report["counts"]["present"] == 1 and report["counts"]["missing"] == 1, "local link results differ")
    require(report["findings"][0]["line"] == 2 and report["findings"][0]["resolved_path"] == "docs/lost.md", "missing link provenance differs")
    arguments["inventory_complete"] = False
    partial = session.tool("check_local_links", arguments)
    require(partial["status"] == "partial" and partial["counts"]["missing"] == 0 and partial["counts"]["unresolved"] == 1, "partial inventory became definitive missing evidence")
    session.tool("check_local_links", {**arguments, "root": "/"}, expected_error=True)
    return {"present": 1, "missing": 1, "source_line": 2, "partial_inventory_unresolved": True,
            "unexpected_filesystem_argument_rejected": True}


def installed_runtime(repo):
    require(sys.flags.isolated, "run this harness with the venv Python -I")
    require(sys.prefix != sys.base_prefix, "a clean virtual environment is required")
    import skills
    package_path = Path(skills.__file__).resolve()
    require(inside(package_path, sys.prefix) and not inside(package_path, repo), "runtime imports source checkout instead of installed wheel")
    config = (Path(sys.prefix) / "pyvenv.cfg").read_text(encoding="utf-8")
    require(re.search(r"include-system-site-packages\s*=\s*false", config, re.I), "venv includes system packages")
    distribution = importlib.metadata.distribution("botte-secrete")
    source_version = re.search(r'^version\s*=\s*"([^"]+)"', (repo / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    require(source_version and source_version.group(1) == distribution.version == skills.__version__, "source, distribution and runtime versions differ")
    scripts = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    command = shutil.which("botte-mcp", path=str(scripts))
    require(command is not None and inside(command, scripts), "installed botte-mcp executable is unavailable")
    return {"version": distribution.version, "isolated": True, "module_in_venv": True,
            "source_checkout_imported": False, "declared_dependencies": len(distribution.requires or [])}, [command]


def verify_wheel_modules(repo, wheel):
    import skills
    installed = Path(skills.__file__).resolve().parent
    members = ("__init__.py", "llm_mcp/server.py", "llm_mcp/lazy.py",
               "preflight/assessment.py", "preflight/policy.py", "skill_finder/finder.py",
               "preflight/evaluation.py", "preflight/evaluation_cases.json",
               "solvers/statistics.py", "fallow_like/file_duplicates.py", "fallow_like/local_links.py")
    hashes = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in members:
            member = "skills/" + name
            digest = hashlib.sha256(archive.read(member)).hexdigest()
            require(digest == sha256(repo / member) == sha256(installed / name),
                    "source, wheel and installed module differ: " + member)
            hashes[member] = digest
    return hashes


def plugin_contract(repo, version):
    marketplace_path = repo / ".agents/plugins/marketplace.json"
    marketplace = read_json(marketplace_path)
    item = next(item for item in marketplace["plugins"] if item["name"] == "botte-secrete")
    root = (repo / item["source"]["path"]).resolve()
    require(item["source"]["source"] == "local" and inside(root, repo), "marketplace plugin does not use this checkout")
    descriptor_path = root / ".codex-plugin/plugin.json"
    descriptor = read_json(descriptor_path)
    require(descriptor["name"] == "botte-secrete" and descriptor["version"] == version, "plugin/runtime metadata version mismatch")
    config_path = (root / descriptor["mcpServers"]).resolve()
    require(inside(config_path, root), "MCP descriptor escapes plugin")
    servers = read_json(config_path)["mcpServers"]
    require(servers == {"botte-llm": {"type": "stdio", "command": "botte-mcp",
             "env": {"BOTTE_MCP_LAZY_TOOLS": "0"}}}, "plugin command or full-catalog setting differs")
    skill_path = (root / descriptor["skills"] / "botte-secrete/SKILL.md").resolve()
    require(inside(skill_path, root) and skill_path.is_file(), "plugin skill is absent")
    return {"status": "structural_checks_passed", "codex_host_installation": "not_tested",
            "files_sha256": {str(path.relative_to(repo)).replace(os.sep, "/"): sha256(path)
                             for path in (marketplace_path, descriptor_path, config_path, skill_path)}}


def portable_guidance(work):
    from skills.preflight import policy
    project = work / "fresh-project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Existing user instructions\n", encoding="utf-8")
    original_agents = (project / "AGENTS.md").read_bytes()
    path = policy.write_default(project)
    require(path is not None and "assess_task" in path.read_text(encoding="utf-8"), "fresh project guidance lacks Parcimonia assessment")
    require(policy.ensure_agents_pointer(project), "project guidance pointer was not added")
    agents = (project / "AGENTS.md").read_bytes()
    require(agents.startswith(original_agents) and b".botte/policy.md" in agents, "user AGENTS content was not preserved")
    require(not policy.ensure_agents_pointer(project) and (project / "AGENTS.md").read_bytes() == agents, "project guidance pointer is not idempotent")
    path.write_text("# User-supplied policy\n", encoding="utf-8")
    require(policy.write_default(project) is None and policy.load(project) == "# User-supplied policy\n", "existing policy was overwritten")
    require(not (project / ".claude").exists(), "guidance verification activated a host hook")
    return {"default_policy_created": True, "existing_agents_preserved": True,
            "existing_policy_preserved": True, "idempotent_pointer": True, "host_hooks_activated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-scope", choices=("full_checkout", "selected_snapshot"), default="full_checkout")
    parser.add_argument("--install-mode", choices=("minimal", "full"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.perf_counter_ns()
    report = {"schema": "botte.parcimonia-candidate/v1", "status": "failed",
              "source_commit": args.source_commit, "source_scope": args.source_scope,
              "install_mode": args.install_mode,
              "python": sys.version.split()[0], "platform": sys.platform,
              "measurement_scope": "installed stdio startup, handshake, advertised native catalog, assessment, execution and fixture assertions; build/install/host reasoning excluded",
              "provider_tokens": None, "cost": None, "savings": None, "scenarios": []}
    try:
        require(re.fullmatch(r"[0-9a-f]{40}", args.source_commit), "source commit must be a full Git SHA")
        repo = args.repo.resolve()
        require(not inside(Path.cwd(), repo), "run the harness outside the source checkout")
        report["wheel_sha256"] = sha256(args.wheel)
        report["runtime"], command = installed_runtime(repo)
        report["runtime"]["source_wheel_installed_sha256"] = verify_wheel_modules(repo, args.wheel)
        report["plugin"] = plugin_contract(repo, report["runtime"]["version"])
        with tempfile.TemporaryDirectory(prefix="parcimonia-installed-") as directory:
            work = Path(directory)
            require(not inside(work, repo), "fixture directory must be outside checkout")
            report["portable_guidance"] = portable_guidance(work)
            for name, verify in (("statistics", statistics), ("file_duplicates", duplicates), ("local_links", links)):
                report["active_scenario"] = name
                scenario_start = time.perf_counter_ns()
                launch_env = read_json(repo / "plugins/botte-secrete/.mcp.json")["mcpServers"]["botte-llm"].get("env", {})
                with Session(command, work, launch_env=launch_env) as session:
                    result = verify(session)
                report["scenarios"].append({"name": name, "status": "passed", "observations": result,
                    "elapsed_ns": time.perf_counter_ns() - scenario_start,
                    "protocol_input_utf8_bytes": session.sent, "protocol_output_utf8_bytes": session.received})
        report["status"] = "passed"
        report.pop("active_scenario", None)
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
    report["harness_elapsed_ns"] = time.perf_counter_ns() - started
    raw = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    require(len(raw.encode("utf-8")) <= MAX_REPORT_BYTES, "report exceeds 64 KiB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(raw)
    print(json.dumps({"status": report["status"], "scenarios_passed": len(report["scenarios"]),
                      "source_commit": args.source_commit, "report": str(args.output),
                      "error": report.get("error")}, ensure_ascii=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
