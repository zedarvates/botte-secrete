"""Private stdio worker: cached Needle 2 inference only, no tool execution.

Run through Needle2ToolRouter. A separate process bounds native inference time
and isolates the engine's process-global conversation from other agents.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

PACKAGE_VERSION = "2.0.13"
MAX_MESSAGE = 65_536


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True)
    args = parser.parse_args()
    # Set before importing Needle. Inference must never fetch assets or report
    # usage, even if the parent shell enables either behaviour.
    os.environ.update(NEEDLE_TELEMETRY="0", DO_NOT_TRACK="1",
                      HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_OFFLINE="1",
                      NEEDLE2_LIB_PATH=str(Path(args.library).resolve()))
    agent = None
    try:
        if importlib.metadata.version("cactus-needle") != PACKAGE_VERSION:
            raise RuntimeError("unsupported_package_version")
        from needle import Needle
        init = json.loads(sys.stdin.buffer.readline(MAX_MESSAGE + 1))
        # JSON schemas only: no decorated/callable tools enter this worker.
        agent = Needle(tools=init["tools"])
        print(json.dumps({"ready": True, "package_version": PACKAGE_VERSION,
                          "python": platform.python_version(), "generation": 2}), flush=True)
        while True:
            line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
            if not line:
                return 0
            if len(line) > MAX_MESSAGE:
                raise ValueError("message_too_large")
            request = json.loads(line)
            agent.reset()
            response = agent.complete(request["query"], max_new_tokens=256)
            print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
    except Exception as error:
        # Native/package errors may contain private paths or input; expose the
        # type only. The parent returns a structured abstention.
        print(json.dumps({"worker_error": type(error).__name__}), flush=True)
        return 1
    finally:
        if agent is not None:
            agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
