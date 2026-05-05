"""Streaming Ollama HTTP client (no paid APIs)."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Generator, Iterable

import requests

CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.DOTALL)


@dataclass
class OllamaModel:
    name: str
    size: int = 0  # bytes
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""

    @property
    def size_human(self) -> str:
        if self.size <= 0:
            return "?"
        n = float(self.size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"


@dataclass
class StreamStats:
    """Filled in as the stream proceeds. Final values are set when done=True."""
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float = 0.0
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_duration_ns: int = 0  # from Ollama
    aborted: bool = False

    @property
    def elapsed_s(self) -> float:
        end = self.finished_at or time.monotonic()
        return max(0.0, end - self.started_at)

    @property
    def tokens_per_sec(self) -> float:
        return (self.response_tokens / self.elapsed_s) if self.elapsed_s > 0 else 0.0


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --- discovery -----------------------------------------------------------

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[OllamaModel]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
        except requests.RequestException:
            return []
        out: list[OllamaModel] = []
        for entry in r.json().get("models", []):
            details = entry.get("details", {}) or {}
            out.append(
                OllamaModel(
                    name=entry.get("name", ""),
                    size=int(entry.get("size", 0) or 0),
                    parameter_size=details.get("parameter_size", ""),
                    quantization=details.get("quantization_level", ""),
                    family=details.get("family", ""),
                )
            )
        return out

    # --- generation ----------------------------------------------------------

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict],
        *,
        temperature: float = 0.2,
        keep_alive: str = "5m",
        stop_event: threading.Event | None = None,
        stats: StreamStats | None = None,
    ) -> Generator[str, None, None]:
        """Yield successive content tokens from /api/chat (stream=true).

        Each message dict supports the standard Ollama format:
            {"role": "user", "content": "...", "images": [base64_str, ...]}

        If `stop_event` is set, the generator closes the connection cleanly
        and marks `stats.aborted = True`.
        """
        payload = {
            "model": model,
            "messages": list(messages),
            "stream": True,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature},
        }
        with requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if stop_event is not None and stop_event.is_set():
                    if stats is not None:
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
                    if stats is not None:
                        stats.finished_at = time.monotonic()
                        stats.prompt_tokens = int(chunk.get("prompt_eval_count", 0) or 0)
                        stats.response_tokens = int(chunk.get("eval_count", 0) or 0)
                        stats.total_duration_ns = int(chunk.get("total_duration", 0) or 0)
                    return

    def pull_stream(self, model: str) -> Generator[dict, None, None]:
        """Stream pull progress from /api/pull. Yields raw status dicts."""
        # Use a generous timeout: connect within 30s, but allow reads to
        # take as long as needed — large model downloads can take hours.
        with requests.post(
            f"{self.base_url}/api/pull",
            json={"name": model, "stream": True},
            stream=True,
            timeout=(30, None),
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


    def generate_once(
        self,
        model: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        keep_alive: str = "5m",
        timeout: float = 60.0,
    ) -> str:
        """Non-streaming call — used for utilities (summarisation, classification)."""
        r = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return ((r.json().get("message") or {}).get("content") or "").strip()


# --- vision detection -------------------------------------------------------


_VISION_MARKERS = ("vl", "llava", "vision", "moondream", "minicpm-v", "qwen2-vl", "qwen2.5-vl")


def model_supports_vision(name: str) -> bool:
    """Best-effort: classify a model name as vision-capable."""
    n = (name or "").lower()
    return any(m in n for m in _VISION_MARKERS)


# --- token estimation / history trimming ------------------------------------


def estimate_tokens(text: str) -> int:
    """Rough chars/4 heuristic. Good enough for budget triage."""
    return max(1, len(text or "") // 4)


def estimate_history_tokens(history: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in history)


def trim_history(
    history: list[dict],
    *,
    max_tokens: int,
    keep_last: int = 4,
    summary_prefix: str = "[summary of earlier turns]\n",
) -> tuple[list[dict], list[dict]]:
    """Split history into (kept, dropped). The caller can summarise `dropped` and
    prepend the summary as a system message.

    Always keeps the last `keep_last` messages; trims older messages until the
    total budget fits. Returns (kept, dropped). If nothing was dropped, returns
    (history, []).
    """
    if estimate_history_tokens(history) <= max_tokens or len(history) <= keep_last:
        return history, []
    kept = list(history[-keep_last:])
    dropped = list(history[:-keep_last])
    # Remove from the front of `dropped` until the rest fits
    while dropped and estimate_history_tokens(dropped + kept) > max_tokens:
        dropped.pop(0)  # safety net — we always keep `kept`
        if not dropped:
            break
    return kept, history[: len(history) - len(kept)]


# --- helpers -----------------------------------------------------------------


def extract_python_code(text: str) -> str:
    """Pull the python block out of a model response.

    Returns the first ```python ... ``` block, or an empty string if no
    fence is found — prose without a code fence is NOT executable Python.
    """
    matches = CODE_FENCE_RE.findall(text)
    if matches:
        return matches[0].strip()
    return ""


# Curated, code-strong models that fit on consumer GPUs. All resolve to Q4_K_M
# by default in Ollama (the quality / size sweet spot).
RECOMMENDED_MODELS: list[tuple[str, str]] = [
    ("qwen2.5-coder:7b", "Code, ~4.7 GB, Q4_K_M — best default"),
    ("qwen2.5-coder:14b", "Code, ~9 GB, Q4_K_M — better reasoning"),
    ("qwen2.5-coder:3b", "Code, ~1.9 GB, Q4_K_M — light VRAM"),
    ("deepseek-coder-v2:16b", "Code, ~9 GB, Q4_0 — strong alternative"),
    ("codellama:13b", "Code, ~7.4 GB, Q4_0"),
    ("llama3.1:8b", "General, ~4.7 GB, Q4_K_M"),
    ("mistral:7b", "General, ~4.1 GB, Q4_0"),
]
