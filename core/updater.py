"""Light-weight GitHub Releases update check (no auto-download — only notifies)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

import requests

# Override these constants at import time if you fork the project
RELEASES_API_URL = "https://api.github.com/repos/Oli97430/UNIFICATION/releases/latest"
RELEASES_HUMAN_URL = "https://github.com/Oli97430/UNIFICATION/releases/latest"


_VER_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse(v: str) -> tuple[int, int, int]:
    m = _VER_RE.search(v or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


@dataclass
class UpdateInfo:
    available: bool
    current: str
    latest: str = ""
    url: str = RELEASES_HUMAN_URL
    notes: str = ""


def check_for_update(current_version: str, *, timeout: float = 4.0) -> Optional[UpdateInfo]:
    """Returns UpdateInfo if reachable, None on network failure (silent)."""
    try:
        r = requests.get(
            RELEASES_API_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if r.status_code == 404:
            # Repo or releases not yet published. Treat as up-to-date silently.
            return UpdateInfo(available=False, current=current_version)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None
    latest = data.get("tag_name") or data.get("name") or ""
    notes = data.get("body") or ""
    return UpdateInfo(
        available=_parse(latest) > _parse(current_version),
        current=current_version,
        latest=latest,
        url=data.get("html_url", RELEASES_HUMAN_URL),
        notes=notes,
    )
