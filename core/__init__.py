"""UNIFICATION core modules."""
from .addon_installer import (
    ADDON_FILE_NAME,
    ADDON_REMOTE_URL,
    BUNDLED_ADDON_PATH,
    BlenderAddonDir,
    fetch_remote_addon,
    find_blender_addon_dirs,
    install_addon,
    open_addon_dir,
    read_bundled_version,
    uninstall_addon,
)
from .blender_client import (
    BlenderClient,
    BlenderResult,
    wrap_with_render,
    wrap_with_view3d_override,
)
from .i18n import LANGUAGE_LABELS, available_languages, get_language, set_language, t
from .lint import LintIssue, lint_python
from .ollama_client import (
    OllamaClient,
    OllamaModel,
    StreamStats,
    estimate_history_tokens,
    estimate_tokens,
    model_supports_vision,
    trim_history,
)
from .settings import HISTORY_PATH, LOG_PATH, Settings, load_history, save_history
from .system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_QUERY, is_query_intent, pick_system_prompt
from .tcp_ping import CREATIVE_APPS, ping_tcp_addon
from .updater import UpdateInfo, check_for_update

__all__ = [
    "ADDON_FILE_NAME",
    "ADDON_REMOTE_URL",
    "BUNDLED_ADDON_PATH",
    "BlenderAddonDir",
    "BlenderClient",
    "BlenderResult",
    "LintIssue",
    "UpdateInfo",
    "check_for_update",
    "estimate_history_tokens",
    "estimate_tokens",
    "is_query_intent",
    "lint_python",
    "model_supports_vision",
    "pick_system_prompt",
    "trim_history",
    "wrap_with_render",
    "wrap_with_view3d_override",
    "SYSTEM_PROMPT_QUERY",
    "LANGUAGE_LABELS",
    "available_languages",
    "get_language",
    "set_language",
    "t",
    "OllamaClient",
    "OllamaModel",
    "Settings",
    "StreamStats",
    "SYSTEM_PROMPT",
    "fetch_remote_addon",
    "find_blender_addon_dirs",
    "install_addon",
    "load_history",
    "open_addon_dir",
    "read_bundled_version",
    "save_history",
    "uninstall_addon",
    "CREATIVE_APPS",
    "ping_tcp_addon",
    "HISTORY_PATH",
    "LOG_PATH",
]
