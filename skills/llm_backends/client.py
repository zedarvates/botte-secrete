"""LocalLLMClient — call local OpenAI-compatible servers (LM Studio, Ollama, …).

This is what actually offloads work from the cloud: the routers decide *that* a
task can go local, this module makes the call. Pure stdlib (urllib), so it adds
no dependencies to the project.

All of LM Studio, Ollama (/v1), LocalAI, vLLM, llama.cpp-server, Jan and
KoboldCpp speak the OpenAI /v1/chat/completions schema, so one client covers
them all.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from skills.llm_backends.discovery import Backend
from skills.llm_backends import registry


class LocalLLMError(RuntimeError):
    """Raised when a local backend call fails."""


@dataclass
class ChatResult:
    text: str
    model: str
    backend: str            # "host:port"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning: str = ""     # populated by "thinking" models (vibethinker, R1, …)
    truncated: bool = False  # finish_reason == "length"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LocalLLMClient:
    """Thin OpenAI-compatible chat client pointed at a local backend."""

    def __init__(self, backend: Optional[Backend] = None, timeout: float = 120.0):
        self.backend = backend or registry.best_chat_backend()
        if self.backend is None:
            raise LocalLLMError(
                "No local chat backend available. Run discovery first: "
                "`python -m skills.llm_backends.cli scan`."
            )
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        url = self.backend.base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     # LM Studio / LocalAI ignore the key; vLLM may require one.
                     "Authorization": "Bearer local"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise LocalLLMError(f"{self.backend.base_url}{path} → HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError) as e:
            raise LocalLLMError(f"{self.backend.base_url}{path} unreachable: {e}")

    def chat(self, prompt: str, *, system: Optional[str] = None,
             model: Optional[str] = None, temperature: float = 0.2,
             max_tokens: int = 1024) -> ChatResult:
        """Single-turn chat completion against the local backend."""
        model = model or registry.preferred_model(self.backend) or "local-model"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = self._post("/v1/chat/completions", {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        })

        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise LocalLLMError(f"Unexpected response shape: {str(payload)[:200]}")

        content = (message.get("content") or "").strip()
        reasoning = (message.get("reasoning_content") or message.get("reasoning") or "").strip()
        # Reasoning models can return empty content (e.g. truncated mid-thought);
        # fall back to the reasoning channel so the caller still gets something.
        text = content or reasoning

        usage = payload.get("usage", {}) or {}
        return ChatResult(
            text=text,
            model=payload.get("model", model),
            backend=f"{self.backend.host}:{self.backend.port}",
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            reasoning=reasoning,
            truncated=choice.get("finish_reason") == "length",
        )


def quick_chat(prompt: str, **kwargs) -> ChatResult:
    """Convenience: pick the best local backend and run one prompt."""
    return LocalLLMClient().chat(prompt, **kwargs)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Réponds en un mot: capitale de la France ?"
    try:
        res = quick_chat(q, max_tokens=64)
        print(f"[{res.backend} · {res.model} · {res.total_tokens} tok]\n{res.text}")
    except LocalLLMError as e:
        print(f"❌ {e}")
