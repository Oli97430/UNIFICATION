"""User settings persisted as JSON next to the application."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".ollamatoblender"
DEFAULT_PATH = CONFIG_DIR / "settings.json"
HISTORY_PATH = CONFIG_DIR / "history.json"
LOG_PATH = CONFIG_DIR / "events.log"


@dataclass
class Settings:
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:32b"
    blender_host: str = "127.0.0.1"
    blender_port: int = 9876
    appearance_mode: str = "dark"  # "dark" | "light" | "system"
    color_theme: str = "blue"
    temperature: float = 0.2
    keep_alive: str = "5m"
    auto_execute: bool = True
    persist_history: bool = True
    window_geometry: str = ""  # "WxH+X+Y"

    # Reliability features
    auto_fix_on_error: bool = True
    max_fix_attempts: int = 1
    auto_render_preview: bool = False
    max_history_tokens: int = 8000
    auto_route_prompt: bool = True
    num_ctx: int = 8192
    inject_scene_context: bool = True

    # Update check
    check_for_updates: bool = True

    # i18n: "auto" | "en" | "fr"
    language: str = "auto"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or DEFAULT_PATH
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f for f in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in data.items() if k in known})
        except (json.JSONDecodeError, TypeError, OSError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or DEFAULT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def load_history(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or HISTORY_PATH
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history: list[dict[str, Any]], path: Path | None = None) -> None:
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
