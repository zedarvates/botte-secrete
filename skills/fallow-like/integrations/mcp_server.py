"""MCP server for fallow-like integration with IDEs."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path
from skills.fallow_like.config import FallowConfig
from skills.fallow_like.cli import run_analysis


async def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    try:
        if method == "analyze":
            config = FallowConfig(
                project_root=Path(params.get("path", ".")),
                output_format=params.get("format", "json"),
            )
            result = run_analysis(config)
            return {"jsonrpc": "2.0", "id": req_id, "result": result.model_dump()}

        elif method == "health":
            config = FallowConfig(project_root=Path(params.get("path", ".")))
            result = run_analysis(config)
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "score": result.health.score,
                "grade": result.health.grade,
                "findings": len(result.findings),
            }}

        elif method == "dead_code":
            config = FallowConfig(
                project_root=Path(params.get("path", ".")),
                enable_duplication=False, enable_complexity=False,
                enable_boundaries=False, enable_feature_flags=False,
                enable_secrets=False, enable_hot_paths=False, enable_blast_radius=False,
            )
            result = run_analysis(config)
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": [f.model_dump() for f in result.dead_code]}

        elif method == "secrets":
            config = FallowConfig(
                project_root=Path(params.get("path", ".")),
                enable_dead_code=False, enable_duplication=False,
                enable_complexity=False, enable_boundaries=False,
                enable_feature_flags=False, enable_hot_paths=False, enable_blast_radius=False,
            )
            result = run_analysis(config)
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": [f.model_dump() for f in result.secrets]}

        else:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    except Exception as e:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(e)}}


async def main():
    """Run MCP server over stdio."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input)
            if not line:
                continue
            request = json.loads(line)
            response = await handle_request(request)
            print(json.dumps(response, default=str), flush=True)
        except EOFError:
            break


if __name__ == "__main__":
    asyncio.run(main())
