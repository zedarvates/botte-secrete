"""llm_backends — discover, register, audit and call local LLM servers.

Public surface:
    discover(...)              find live backends on host(s)/network
    registry.refresh(...)      discover + persist to configs/llm-endpoints.json
    registry.load()            read the persisted registry
    LocalLLMClient / quick_chat   call a local OpenAI-compatible model
    audit(...)                 local-usage audit + hardware-aware setup advice
"""

from skills.llm_backends.discovery import Backend, discover, scan_host
from skills.llm_backends.client import LocalLLMClient, ChatResult, quick_chat, LocalLLMError
from skills.llm_backends.audit import audit, profile_hardware, recommend_model
from skills.llm_backends import registry

__all__ = [
    "Backend", "discover", "scan_host",
    "LocalLLMClient", "ChatResult", "quick_chat", "LocalLLMError",
    "audit", "profile_hardware", "recommend_model",
    "registry",
]
