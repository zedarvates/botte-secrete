"""MCP server compatibility entrypoint.

The original implementation is kept in :mod:`skills.llm_mcp.server_impl`.
This narrow wrapper preserves its public and private module surface while
repairing the ``loop_stats`` dispatch handler. It can be removed once the
implementation file is edited directly and the regression tests remain green.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Preserve direct-script compatibility as well as ``python -m`` execution.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.llm_mcp import server_impl as _impl  # noqa: E402

# Re-export the complete previous module surface, including private helpers that
# downstream tests or local integrations may import. Dunder metadata stays
# owned by this wrapper so ``__name__ == '__main__'`` remains correct.
for _name, _value in vars(_impl).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value


def _tool_loop_stats(_args: dict) -> str:
    """Return aggregate loop-ledger metrics as compact JSON."""
    from skills.loop_optimizer.ledger import LoopLedger

    ledger = LoopLedger()
    return json.dumps(
        ledger.summarize(ledger.read()),
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ``handle`` is defined in server_impl and reads the same mutable mapping.
DISPATCH["loop_stats"] = _tool_loop_stats


if __name__ == "__main__":
    raise SystemExit(main())
