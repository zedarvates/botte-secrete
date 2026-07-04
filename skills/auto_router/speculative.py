"""Speculative local execution — launch local + cloud in parallel, keep first response.

For tasks at the CHEAP/STANDARD boundary, run both backends simultaneously
and return the first successful response. If local completes first → 0 cloud cost.
If cloud completes first → pay cloud but get faster response.

Pattern — not yet wired into decide() by default. Import and use explicitly.
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional


def speculative_run(prompt: str, task_type: str = "", timeout: float = 30.0) -> dict:
    """Run local and cloud in parallel, return first success."""
    from skills.auto_router.router import AutoRouter
    from skills.llm_backends.client import LocalLLMClient

    router = AutoRouter()

    def try_local():
        try:
            client = LocalLLMClient()
            return client.chat(prompt, max_tokens=512)
        except Exception:
            return None

    def try_cloud():
        try:
            return router.run(prompt, task_type=task_type, force_tier=None)
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        local_future = executor.submit(try_local)
        cloud_future = executor.submit(try_cloud)

        done, _ = concurrent.futures.wait(
            [local_future, cloud_future],
            timeout=timeout,
            return_when=concurrent.futures.FIRST_COMPLETED,
        )

        for future in done:
            result = future.result()
            if result is not None:
                return {"answer": result, "source": "speculative", "cloud_tokens": 0}

    return {"answer": None, "source": "timeout", "cloud_tokens": 0}
