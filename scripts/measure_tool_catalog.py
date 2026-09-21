"""Measure the full/lazy MCP catalogs; never infer whole-agent savings.

Optional: --tokens uses an already installed tiktoken and cached o200k_base.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def measure(counter=None, tokenizer=None) -> dict:
    from skills.llm_mcp.lazy import lazy_tool_list
    from skills.llm_mcp.server import TOOLS

    catalogs = {}
    for name, items in (("full", TOOLS), ("lazy", lazy_tool_list(TOOLS))):
        rendered = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        encoded = rendered.encode("utf-8")
        catalogs[name] = {
            "tool_count": len(items), "utf8_bytes": len(encoded),
            "tokens": counter(rendered) if counter else None,
            "serialized_sha256": hashlib.sha256(encoded).hexdigest(),
        }
    return {
        "schema": "botte.tool-catalog-measurement/v1",
        "scope": "one serialized tool catalog; component measurement only",
        "serialization": "json.dumps(ensure_ascii=False, separators=(',', ':'))",
        "catalogs": catalogs,
        "tokenizer": tokenizer or {"status": "not_measured"},
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ("skills/llm_mcp/server.py", "skills/llm_mcp/lazy.py",
                                       "scripts/measure_tool_catalog.py")},
        "llm_calls": 0,
        "excluded": ["lookup requests and responses", "agent messages and tool results",
                     "provider accounting", "prompt cache", "agent turns and task quality"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", action="store_true")
    args = parser.parse_args()
    counter = None
    tokenizer = None
    with patch("socket.socket.connect", side_effect=RuntimeError("offline measurement")):
        if args.tokens:
            import tiktoken
            encoding = tiktoken.get_encoding("o200k_base")
            counter = lambda value: len(encoding.encode(value, disallowed_special=()))
            tokenizer = {"status": "measured", "name": encoding.name,
                         "library": "tiktoken", "version": importlib.metadata.version("tiktoken")}
        print(json.dumps(measure(counter, tokenizer), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
