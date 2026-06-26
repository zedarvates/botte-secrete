"""dispatcher — dispatch les appels MCP tools/call vers la bonne skill Botte.

Chaque appel est exécuté via subprocess (sandbox) avec les arguments fournis.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from skills.mcp_gateway.registry import SkillTool


REPO_ROOT = Path(__file__).resolve().parents[2]


class Dispatcher:
    """Dispatch MCP tool calls to Botte skills via subprocess."""

    def __init__(self):
        self.repo_root = REPO_ROOT

    def call(self, tool: SkillTool, arguments: dict[str, Any]) -> dict:
        """Call a Botte skill with the given arguments.

        Args:
            tool: The SkillTool to invoke.
            arguments: Dict of argument name → value.

        Returns:
            dict with 'content' (list of text content) or 'isError' (bool).
        """
        # Build command: python -m skills.<name>.cli <subcommand> <args>
        subcmd = tool.name.replace("_", "-")  # some skills use hyphens

        # Determine subcommand from tool name
        subcommand_map = {
            "security_scanner": "scan",
            "fast_context": "explore",
            "meta_harness": "run",
            "botte_nn": "predict",
            "solvers": None,
            "context_budget": None,
            "nlp_deterministic": None,
            "checkup": None,
            "infra_advisor": "auto",
            "llm_backends": "audit",
            "metrics": None,
        }
        subcmd = subcommand_map.get(tool.name, "")

        # Build argument list from tool definition + user arguments
        cmd_args = []

        # Add subcommand if defined
        if subcmd:
            cmd_args.append(subcmd)

        # Root / target argument
        if "root" in arguments:
            cmd_args.append(str(arguments.pop("root")))
        elif "target" in arguments:
            cmd_args.append(str(arguments.pop("target")))

        # Query or model argument (for fast_context / botte_nn)
        if "query" in arguments:
            cmd_args.append(str(arguments.pop("query")))
        if "model" in arguments and "input" in arguments:
            cmd_args.append(str(arguments.pop("model")))
            cmd_args.append("--input")
            input_vals = arguments.pop("input")
            if isinstance(input_vals, list):
                cmd_args.extend(str(v) for v in input_vals)
            else:
                cmd_args.append(str(input_vals))

        # Remaining arguments
        for key, value in arguments.items():
            flag = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    cmd_args.append(flag)
            elif isinstance(value, (int, float)):
                cmd_args.extend([flag, str(value)])
            elif isinstance(value, str):
                cmd_args.extend([flag, value])
            elif isinstance(value, list):
                cmd_args.append(flag)
                cmd_args.extend(str(v) for v in value)

        full_cmd = ["python3", "-m", tool.module_path] + cmd_args

        try:
            result = subprocess.run(
                full_cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return self._error(f"Timeout (120s) executing {tool.name}")
        except FileNotFoundError:
            return self._error(f"Command not found: {' '.join(full_cmd[:2])}")

        if result.returncode == 0:
            return self._ok(result.stdout)
        else:
            return self._ok(result.stderr if result.stderr else result.stdout)

    def _ok(self, text: str) -> dict:
        return {
            "content": [{"type": "text", "text": text.strip()}],
        }

    def _error(self, msg: str) -> dict:
        return {
            "content": [{"type": "text", "text": msg}],
            "isError": True,
        }
