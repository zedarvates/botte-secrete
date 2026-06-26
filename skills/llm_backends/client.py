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
             max_tokens: int = 1024, response_format: Optional[dict] = None,
             grammar: Optional[str] = None) -> ChatResult:
        """Single-turn chat completion against the local backend.

        `response_format` / `grammar` constrain the output so a small local model
        cannot drift into free-form hallucination:
            response_format={"type": "json_object"}        → valid JSON (OpenAI /v1)
            response_format={"type": "json_schema", ...}    → schema-constrained
            grammar=<GBNF string>                            → llama.cpp grammar
        Both are sent only when set, so plain backends are unaffected.
        """
        model = model or registry.preferred_model(self.backend) or "local-model"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if grammar is not None:
            body["grammar"] = grammar  # llama.cpp-server extension; ignored elsewhere

        payload = self._post("/v1/chat/completions", body)

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

    def chat_json(self, prompt: str, *, schema: Optional[dict] = None,
                  system: Optional[str] = None, model: Optional[str] = None,
                  max_tokens: int = 512, retries: int = 1) -> dict:
        """Chat that MUST return a JSON object — parsed locally, returned as a dict.

        The anti-hallucination workhorse: the model is constrained to JSON (schema-
        constrained when `schema` is given), the reply is parsed here, and on failure
        we retry once with a corrective nudge before raising. The caller gets data,
        never prose — a small model cannot answer with a confident paragraph of fiction.
        """
        if schema is not None:
            rf = {"type": "json_schema",
                  "json_schema": {"name": "out", "schema": schema, "strict": True}}
        else:
            rf = {"type": "json_object"}
        sys_msg = ((system or "") +
                   "\nRespond with a single valid JSON object only. No prose, no markdown.").strip()
        last = ""
        for _ in range(retries + 1):
            res = self.chat(prompt, system=sys_msg, model=model, temperature=0.0,
                            max_tokens=max_tokens, response_format=rf)
            last = res.text
            obj = _extract_json(res.text)
            if obj is not None:
                return obj
            prompt = (f"{prompt}\n\nYour previous reply was not valid JSON:\n"
                      f"{res.text[:200]}\nReturn ONLY a valid JSON object.")
        raise LocalLLMError(
            f"local model did not return valid JSON after {retries + 1} tries: {last[:200]}")


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort parse of a JSON object from a model reply (tolerates ``` fences
    and surrounding prose). Returns the dict, or None if nothing valid is found."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):  # ```json … ``` fence
        parts = s.split("```")
        s = parts[1] if len(parts) >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = s.find("{")  # fall back to the first balanced {...}
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def gbnf_for_enum(labels: list[str]) -> str:
    """GBNF grammar forcing the output to be exactly one of `labels` (a JSON string).

    For llama.cpp's `grammar` field — a classification then cannot hallucinate a
    label outside the closed set. e.g. ['local','cloud'] → root ::= "local" | "cloud"
    """
    alts = " | ".join(json.dumps(label) for label in labels)
    return f"root ::= {alts}"


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
