"""Dry cloud provider — simulate cloud without API key for CI/testing.

    from skills.auto_router.providers import DryCloudProvider
    p = DryCloudProvider()
    p.chat("test")  # returns mock response, never calls real API
"""

from __future__ import annotations


class DryCloudProvider:
    """Simulates a cloud provider without needing API keys."""

    def __init__(self, label: str = "dry-cloud", model: str = "dry-model"):
        self.label = label
        self.model = model
        self.api_key = ""
        self.base_url = "http://localhost:1"  # unreachable
        self.tier = 2  # CHEAP equivalent
        self.via = "dry"

    def chat(self, prompt: str, system: str = "", max_tokens: int = 512) -> dict:
        """Return a deterministic mock response."""
        return {
            "text": f"[DRY] Mock response for: {prompt[:50]}...",
            "tokens": len(prompt.split()) + 10,
        }

    def chat_stream(self, prompt: str, **kwargs):
        yield "[DRY] Mock stream response"
