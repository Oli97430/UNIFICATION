"""Unified streaming LLM providers — Ollama, Claude, OpenAI, Gemini.

All providers expose the same `chat_stream()` interface so the rest of
the app never needs to know which backend is active.  Only `requests`
is needed (already a dependency); no vendor SDKs required.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Generator, Iterable

import requests

from .ollama_client import StreamStats

# ---------------------------------------------------------------- helpers

_TIMEOUT = 600.0  # global read timeout for cloud APIs


def _sse_lines(response: requests.Response):
    """Yield decoded lines from a Server-Sent Events stream."""
    for line in response.iter_lines(decode_unicode=True):
        if line:
            yield line


# ================================================================ base
# ================================================================

class LLMProvider:
    """Abstract base for all LLM providers."""

    name: str = "base"
    needs_api_key: bool = False

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ) -> Generator[str, None, None]:
        raise NotImplementedError

    def is_alive(self) -> bool:
        return False

    def list_models(self) -> list[str]:
        return []


# ================================================================ Ollama
# ================================================================

class OllamaProvider(LLMProvider):
    """Local Ollama instance — wraps the existing HTTP API."""

    name = "ollama"
    needs_api_key = False

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
        except requests.RequestException:
            return []

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ) -> Generator[str, None, None]:
        payload = {
            "model": model,
            "messages": list(messages),
            "stream": True,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
        with requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if stop_event and stop_event.is_set():
                    if stats:
                        stats.aborted = True
                        stats.finished_at = time.monotonic()
                    r.close()
                    return
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk.get("message") or {}
                token = msg.get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    if stats:
                        stats.finished_at = time.monotonic()
                        stats.prompt_tokens = int(chunk.get("prompt_eval_count", 0) or 0)
                        stats.response_tokens = int(chunk.get("eval_count", 0) or 0)
                        stats.total_duration_ns = int(chunk.get("total_duration", 0) or 0)
                    return


# ================================================================ Claude (Anthropic)
# ================================================================

CLAUDE_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class ClaudeProvider(LLMProvider):
    """Anthropic Messages API with streaming."""

    name = "claude"
    needs_api_key = True

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[str]:
        return list(CLAUDE_MODELS)

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ) -> Generator[str, None, None]:
        msgs = list(messages)
        # Anthropic requires system as a top-level param, not in messages
        system_text = ""
        chat_msgs = []
        for m in msgs:
            if m.get("role") == "system":
                system_text += m.get("content", "") + "\n"
            else:
                # Anthropic uses {"role": "user"/"assistant", "content": "..."}
                chat_msgs.append({"role": m["role"], "content": m.get("content", "")})

        # Ensure messages alternate user/assistant (Anthropic requirement)
        chat_msgs = _fix_alternation(chat_msgs)

        payload = {
            "model": model,
            "max_tokens": num_ctx,
            "temperature": temperature,
            "stream": True,
            "messages": chat_msgs,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        token_count = 0
        with requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            stream=True,
            timeout=_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in _sse_lines(r):
                if stop_event and stop_event.is_set():
                    if stats:
                        stats.aborted = True
                        stats.finished_at = time.monotonic()
                    r.close()
                    return
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                evt_type = evt.get("type", "")
                if evt_type == "content_block_delta":
                    delta = evt.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        token_count += 1
                        yield text
                elif evt_type == "message_delta":
                    usage = evt.get("usage", {})
                    if stats:
                        stats.response_tokens = usage.get("output_tokens", token_count)
                elif evt_type == "message_start":
                    usage = evt.get("message", {}).get("usage", {})
                    if stats:
                        stats.prompt_tokens = usage.get("input_tokens", 0)
        if stats and not stats.finished_at:
            stats.finished_at = time.monotonic()
            if not stats.response_tokens:
                stats.response_tokens = token_count


# ================================================================ OpenAI
# ================================================================

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o4-mini",
    "o3",
    "o3-mini",
]


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API with streaming."""

    name = "openai"
    needs_api_key = True

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[str]:
        return list(OPENAI_MODELS)

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ) -> Generator[str, None, None]:
        msgs = list(messages)
        # OpenAI accepts system role directly, just clean up
        chat_msgs = []
        for m in msgs:
            chat_msgs.append({
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
            })

        payload = {
            "model": model,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": num_ctx,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        token_count = 0
        with requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            stream=True,
            timeout=_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in _sse_lines(r):
                if stop_event and stop_event.is_set():
                    if stats:
                        stats.aborted = True
                        stats.finished_at = time.monotonic()
                    r.close()
                    return
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                # Usage info (final chunk)
                usage = chunk.get("usage")
                if usage and stats:
                    stats.prompt_tokens = usage.get("prompt_tokens", 0)
                    stats.response_tokens = usage.get("completion_tokens", token_count)
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        token_count += 1
                        yield text
        if stats and not stats.finished_at:
            stats.finished_at = time.monotonic()
            if not stats.response_tokens:
                stats.response_tokens = token_count


# ================================================================ Gemini
# ================================================================

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


class GeminiProvider(LLMProvider):
    """Google Gemini API with streaming."""

    name = "gemini"
    needs_api_key = True

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[str]:
        return list(GEMINI_MODELS)

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ) -> Generator[str, None, None]:
        msgs = list(messages)
        # Gemini uses "contents" with role "user"/"model" and system_instruction
        system_text = ""
        contents = []
        for m in msgs:
            if m.get("role") == "system":
                system_text += m.get("content", "") + "\n"
            else:
                role = "model" if m.get("role") == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": m.get("content", "")}],
                })

        # Ensure messages alternate user/model
        contents = _fix_alternation_gemini(contents)

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": num_ctx,
            },
        }
        if system_text.strip():
            payload["system_instruction"] = {
                "parts": [{"text": system_text.strip()}],
            }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:streamGenerateContent"
            f"?key={self.api_key}&alt=sse"
        )

        token_count = 0
        with requests.post(
            url,
            json=payload,
            stream=True,
            timeout=_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in _sse_lines(r):
                if stop_event and stop_event.is_set():
                    if stats:
                        stats.aborted = True
                        stats.finished_at = time.monotonic()
                    r.close()
                    return
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                candidates = chunk.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            token_count += 1
                            yield text
                # Usage metadata
                usage = chunk.get("usageMetadata")
                if usage and stats:
                    stats.prompt_tokens = usage.get("promptTokenCount", 0)
                    stats.response_tokens = usage.get("candidatesTokenCount", token_count)
        if stats and not stats.finished_at:
            stats.finished_at = time.monotonic()
            if not stats.response_tokens:
                stats.response_tokens = token_count


# ================================================================ helpers
# ================================================================

def _fix_alternation(msgs: list[dict]) -> list[dict]:
    """Ensure messages strictly alternate user/assistant (Anthropic requirement).

    Merges consecutive same-role messages.  Guarantees first message is 'user'.
    """
    if not msgs:
        return [{"role": "user", "content": "Hello."}]
    out: list[dict] = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n" + m.get("content", "")
        else:
            out.append(dict(m))
    # Must start with user
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "Hello."})
    return out


def _fix_alternation_gemini(contents: list[dict]) -> list[dict]:
    """Ensure Gemini contents alternate user/model. Merge consecutive same-role."""
    if not contents:
        return [{"role": "user", "parts": [{"text": "Hello."}]}]
    out: list[dict] = []
    for c in contents:
        if out and out[-1]["role"] == c["role"]:
            out[-1]["parts"].extend(c.get("parts", []))
        else:
            out.append(dict(c))
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "parts": [{"text": "Hello."}]})
    return out


# ================================================================ registry
# ================================================================

PROVIDERS: dict[str, type[LLMProvider]] = {
    "ollama":  OllamaProvider,
    "claude":  ClaudeProvider,
    "openai":  OpenAIProvider,
    "gemini":  GeminiProvider,
}

PROVIDER_LABELS: dict[str, str] = {
    "ollama":  "Ollama (local)",
    "claude":  "Claude (Anthropic)",
    "openai":  "OpenAI",
    "gemini":  "Gemini (Google)",
}


def create_provider(name: str, **kwargs) -> LLMProvider:
    """Instantiate a provider by registry name."""
    cls = PROVIDERS.get(name, OllamaProvider)
    return cls(**kwargs)
