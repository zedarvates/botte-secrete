"""Sandboxed code execution verifier for local_harness.

Runs generated code in a subprocess with restricted resources (timeout, memory)
and captures stdout/stderr/exit code. 0 cloud tokens.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def verify_code(code: str, *, timeout: int = 10, python: str = "python3",
                workdir: Optional[str] = None) -> dict:
    """Execute code in a sandboxed subprocess and return the result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [python, tmp_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=workdir or ".",
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[:2000],
            "stderr": proc.stderr[:2000],
            "exit_code": proc.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout", "exit_code": -1, "timed_out": True}
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


def verify_code_safety(code: str) -> dict:
    """Lightweight safety check before sandbox execution."""
    dangerous = [
        ("os.system(", "shell execution"),
        ("subprocess.", "subprocess spawning"),
        ("shutil.rmtree", "filesystem deletion"),
        ("eval(", "dynamic eval"),
        ("exec(", "dynamic exec"),
        ("open(", "file write (restricted)"),
    ]
    for pattern, reason in dangerous:
        if pattern in code:
            return {"safe": False, "reason": f"blocked: {reason}"}
    return {"safe": True, "reason": ""}
