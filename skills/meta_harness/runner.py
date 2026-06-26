"""runner — exécute chaque étape dans un sandbox isolé (subprocess + workdir).

Chaque étape tourne dans :
- Son propre dossier de travail (.botte-sandbox/<agent>/)
- Un subprocess isolé avec timeout
- Stdout/stderr capturés
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration: float


class Sandbox:
    """Isolated execution environment for a pipeline step."""

    def __init__(self, workdir: str, sandbox_dir: str = ".botte-sandbox/default",
                 timeout: int = 300):
        self.workdir = str(Path(workdir).resolve())
        self.sandbox_dir = str(Path(self.workdir) / sandbox_dir)
        self.timeout = timeout

    def run(self, command: list[str], args: list[str] | None = None,
            env: dict | None = None) -> SandboxResult:
        """Run a command in the sandbox.

        Creates sandbox dir if needed, runs subprocess, returns result.
        """
        Path(self.sandbox_dir).mkdir(parents=True, exist_ok=True)

        full_cmd = list(command) + (args or [])

        # Merge env: inherit parent + add sandbox-specific vars
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        run_env["BOTTE_SANDBOX"] = self.sandbox_dir

        t0 = time.time()
        try:
            result = subprocess.run(
                full_cmd,
                cwd=self.sandbox_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=run_env,
            )
            duration = round(time.time() - t0, 3)
            return SandboxResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration=duration,
            )
        except subprocess.TimeoutExpired:
            duration = round(time.time() - t0, 3)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"TIMEOUT after {self.timeout}s",
                exit_code=124,
                duration=duration,
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Command not found: {full_cmd[0]}",
                exit_code=127,
                duration=0.0,
            )

    def cleanup(self):
        """Remove sandbox directory."""
        shutil.rmtree(self.sandbox_dir, ignore_errors=True)
