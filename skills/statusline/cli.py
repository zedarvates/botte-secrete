"""CLI/hook entry point for the statusline.

Works both as a plain command and as a Claude Code `statusLine` hook (which
pipes a JSON payload on stdin describing the session; we best-effort read
`cwd`/`workspace`/`project_dir` from it and fall back to the current
directory otherwise — never raises, always prints *something*).

    python -m skills.statusline.cli [project]
"""

from __future__ import annotations

import json
import sys

from skills.console_utf8 import force_utf8
from skills.statusline.statusline import render


def _project_from_stdin() -> str | None:
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
    except Exception:
        return None
    for key in ("cwd", "workspace", "project_dir", "workspace_dir"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def main(argv=None) -> int:
    force_utf8()
    argv = list(argv or sys.argv[1:])
    project = argv[0] if argv else (_project_from_stdin() or ".")
    print(render(project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
