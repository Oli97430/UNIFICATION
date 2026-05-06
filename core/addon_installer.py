"""Detect creative-app install dirs and install / update MCP addons.

Supports: Blender, FreeCAD, GIMP.
Inkscape and Photoshop use standalone servers — no in-app installation needed.
"""
from __future__ import annotations

import platform
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Blender
ADDON_FILE_NAME = "blender_mcp_addon.py"
ADDON_REMOTE_URL = (
    "https://raw.githubusercontent.com/Oli97430/blender-mcp-addon/main/blender_mcp_addon.py"
)
BUNDLED_ADDON_PATH = ASSETS_DIR / ADDON_FILE_NAME

# FreeCAD
FREECAD_ADDON_FILE = "freecad_mcp_addon.py"
BUNDLED_FREECAD_PATH = ASSETS_DIR / FREECAD_ADDON_FILE

# GIMP
GIMP_ADDON_FILE = "gimp_mcp_addon.py"
BUNDLED_GIMP_PATH = ASSETS_DIR / GIMP_ADDON_FILE

VERSION_RE = re.compile(r'"version"\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')


# ---------------------------------------------------------------- discovery


@dataclass
class BlenderAddonDir:
    """A `<blender>/<version>/scripts/addons/` directory we can install into."""
    version: str          # "4.2", "4.5", "5.0", ...
    path: Path            # full path to the addons directory
    installed_version: str = ""   # tuple-style, e.g. "1.3.0", empty if absent

    @property
    def label(self) -> str:
        return f"Blender {self.version}  —  {self.path}"

    @property
    def is_installed(self) -> bool:
        return bool(self.installed_version)

    @property
    def addon_file(self) -> Path:
        return self.path / ADDON_FILE_NAME


def _candidate_roots() -> list[Path]:
    """Possible parents of the per-version Blender config dirs on this OS."""
    home = Path.home()
    system = platform.system()
    roots: list[Path] = []

    if system == "Windows":
        appdata = Path(sys.executable).drive  # placeholder, replaced below
        appdata_env = (
            Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender"
        )
        roots.append(appdata_env)
        # Some installs use the portable layout next to blender.exe — we can't auto-detect that,
        # so we skip it. The user can paste the path manually.
    elif system == "Darwin":
        roots.append(home / "Library" / "Application Support" / "Blender")
    else:  # Linux / *BSD
        roots.append(home / ".config" / "blender")
        # Snap / flatpak fallback
        roots.append(home / "snap" / "blender" / "current" / ".config" / "blender")
        roots.append(home / ".var" / "app" / "org.blender.Blender" / "config" / "blender")
    return [r for r in roots if r.exists()]


_VERSION_DIR_RE = re.compile(r"^(\d+)\.(\d+)$")


def find_blender_addon_dirs() -> list[BlenderAddonDir]:
    """Return one entry per detected `<root>/<X.Y>/scripts/addons/` directory."""
    found: list[BlenderAddonDir] = []
    for root in _candidate_roots():
        for child in sorted(root.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if not _VERSION_DIR_RE.match(child.name):
                continue
            addons = child / "scripts" / "addons"
            if not addons.exists():
                # Older / pristine installs may not have created it yet — still a valid target.
                pass
            installed = read_installed_version(addons / ADDON_FILE_NAME)
            found.append(
                BlenderAddonDir(
                    version=child.name,
                    path=addons,
                    installed_version=installed,
                )
            )
    return found


def read_installed_version(file_path: Path) -> str:
    if not file_path.exists():
        return ""
    try:
        head = file_path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    m = VERSION_RE.search(head)
    if not m:
        return ""
    return ".".join(m.groups())


def read_bundled_version() -> str:
    return read_installed_version(BUNDLED_ADDON_PATH)


def read_addon_name(file_path: Path = BUNDLED_ADDON_PATH) -> str:
    if not file_path.exists():
        return "MCP Server"
    try:
        head = file_path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return "MCP Server"
    m = NAME_RE.search(head)
    return m.group(1) if m else "MCP Server"


# ---------------------------------------------------------------- install


def fetch_remote_addon(timeout: float = 10.0) -> bytes:
    """Download the latest addon source from the official repo."""
    r = requests.get(ADDON_REMOTE_URL, timeout=timeout)
    r.raise_for_status()
    return r.content


def install_addon(target: BlenderAddonDir, source: str = "remote") -> Path:
    """Write the addon file to `target.path / blender_mcp_addon.py`.

    `source`:
        "remote"  — download from GitHub (falls back to bundled on failure)
        "bundled" — always use the file shipped with the app
    """
    target.path.mkdir(parents=True, exist_ok=True)
    dest = target.addon_file

    payload: bytes
    if source == "bundled":
        payload = BUNDLED_ADDON_PATH.read_bytes()
    else:
        try:
            payload = fetch_remote_addon()
        except Exception:
            if not BUNDLED_ADDON_PATH.exists():
                raise
            payload = BUNDLED_ADDON_PATH.read_bytes()

    if dest.exists():
        backup = dest.with_suffix(dest.suffix + ".bak")
        try:
            shutil.copy2(dest, backup)
        except OSError:
            pass

    dest.write_bytes(payload)
    target.installed_version = read_installed_version(dest)
    return dest


def uninstall_addon(target: BlenderAddonDir) -> bool:
    if target.addon_file.exists():
        try:
            target.addon_file.unlink()
            target.installed_version = ""
            return True
        except OSError:
            return False
    return False


def open_addon_dir(target: BlenderAddonDir) -> bool:
    """Open the addon directory in the OS file explorer."""
    target.path.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() == "Windows":
            import os
            os.startfile(str(target.path))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            import subprocess
            subprocess.Popen(["open", str(target.path)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(target.path)])
        return True
    except Exception:
        return False


# ================================================================ generic multi-app support
# FreeCAD, GIMP — detect install dirs and install bundled addons.
# Inkscape & Photoshop are standalone servers (no in-app installation).


@dataclass
class AppAddonDir:
    """A directory we can install a creative-app MCP addon into."""
    app: str              # "freecad" | "gimp"
    label: str            # human label, e.g. "FreeCAD — Macro" or "GIMP 2.10"
    path: Path            # target directory
    addon_filename: str   # "freecad_mcp_addon.py" etc.
    bundled_path: Path    # path to bundled source file in assets/
    installed_version: str = ""
    needs_subfolder: bool = False   # GIMP 3.0+ requires plugin in same-name subfolder

    @property
    def is_installed(self) -> bool:
        return bool(self.installed_version)

    @property
    def addon_file(self) -> Path:
        if self.needs_subfolder:
            stem = Path(self.addon_filename).stem
            return self.path / stem / self.addon_filename
        return self.path / self.addon_filename


# ---- FreeCAD discovery

_FREECAD_VER_RE = re.compile(r"^v?\d+[\.\-]\d+")


def _freecad_config_roots() -> list[Path]:
    """Possible FreeCAD config root directories on this OS."""
    home = Path.home()
    system = platform.system()
    roots: list[Path] = []
    if system == "Windows":
        roots.append(home / "AppData" / "Roaming" / "FreeCAD")
    elif system == "Darwin":
        roots.append(home / "Library" / "Application Support" / "FreeCAD")
        roots.append(home / "Library" / "Preferences" / "FreeCAD")
    else:
        roots.append(home / ".local" / "share" / "FreeCAD")
        roots.append(home / ".config" / "FreeCAD")
        roots.append(home / ".FreeCAD")  # legacy
    return [r for r in roots if r.exists()]


def _freecad_macro_dirs() -> list[Path]:
    """Find all FreeCAD Macro directories.

    FreeCAD layout varies by version:
      - Legacy (< 1.0):  <root>/Macro/
      - Modern (>= 1.0): <root>/v1-1/Macro/  (versioned subdirectory)
    We scan for both patterns.
    """
    candidates: list[Path] = []
    for root in _freecad_config_roots():
        # Legacy: direct Macro/ under root
        legacy = root / "Macro"
        if legacy.is_dir():
            candidates.append(legacy)
        # Modern: versioned subdirectories (v1-1, v1-2, 0.21, etc.)
        for child in sorted(root.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if not _FREECAD_VER_RE.match(child.name):
                continue
            macro = child / "Macro"
            if macro.is_dir():
                candidates.append(macro)
            elif child.is_dir():
                # Version dir exists but Macro/ not yet created — still a valid target
                candidates.append(macro)
    return candidates


def find_freecad_addon_dirs() -> list[AppAddonDir]:
    """Detect FreeCAD Macro directories where we can install the addon."""
    found: list[AppAddonDir] = []
    seen: set[Path] = set()
    for macro_dir in _freecad_macro_dirs():
        if macro_dir in seen:
            continue
        seen.add(macro_dir)
        # Derive version label from path
        parent_name = macro_dir.parent.name
        if _FREECAD_VER_RE.match(parent_name):
            ver = parent_name.replace("-", ".")
            label = f"FreeCAD {ver}  —  {macro_dir}"
        else:
            label = f"FreeCAD  —  {macro_dir}"
        installed = read_installed_version(macro_dir / FREECAD_ADDON_FILE) if macro_dir.exists() else ""
        found.append(AppAddonDir(
            app="freecad",
            label=label,
            path=macro_dir,
            addon_filename=FREECAD_ADDON_FILE,
            bundled_path=BUNDLED_FREECAD_PATH,
            installed_version=installed,
        ))
    return found


# ---- GIMP discovery

_GIMP_VER_RE = re.compile(r"^(\d+)\.(\d+)$")


def _gimp_plugin_roots() -> list[tuple[Path, bool]]:
    """Return (path, needs_subfolder) for each GIMP version found.

    GIMP 2.x: plug-ins folder accepts loose .py files.
    GIMP 3.x: each plugin must be in a subfolder with the same name.
    """
    home = Path.home()
    system = platform.system()
    roots: list[Path] = []

    if system == "Windows":
        roots.append(home / "AppData" / "Roaming" / "GIMP")
    elif system == "Darwin":
        roots.append(home / "Library" / "Application Support" / "GIMP")
    else:
        roots.append(home / ".config" / "GIMP")
        roots.append(home / "snap" / "gimp" / "current" / ".config" / "GIMP")
        roots.append(home / ".var" / "app" / "org.gimp.GIMP" / "config" / "GIMP")

    results: list[tuple[Path, bool]] = []
    for root in roots:
        if not root.exists():
            continue
        for child in sorted(root.iterdir(), reverse=True):
            if not child.is_dir() or not _GIMP_VER_RE.match(child.name):
                continue
            plugins_dir = child / "plug-ins"
            major = int(child.name.split(".")[0])
            needs_sub = major >= 3
            results.append((plugins_dir, needs_sub))
    return results


def find_gimp_addon_dirs() -> list[AppAddonDir]:
    """Detect GIMP plug-ins directories where we can install the addon."""
    found: list[AppAddonDir] = []
    for plugins_dir, needs_sub in _gimp_plugin_roots():
        # Check installed version
        if needs_sub:
            stem = Path(GIMP_ADDON_FILE).stem
            target = plugins_dir / stem / GIMP_ADDON_FILE
        else:
            target = plugins_dir / GIMP_ADDON_FILE
        installed = read_installed_version(target) if target.exists() else ""
        # Derive GIMP version label from path
        gimp_ver = plugins_dir.parent.name  # "2.10" or "3.0"
        found.append(AppAddonDir(
            app="gimp",
            label=f"GIMP {gimp_ver}  —  {plugins_dir}",
            path=plugins_dir,
            addon_filename=GIMP_ADDON_FILE,
            bundled_path=BUNDLED_GIMP_PATH,
            installed_version=installed,
            needs_subfolder=needs_sub,
        ))
    return found


# ---- generic install / uninstall for AppAddonDir

def install_app_addon(target: AppAddonDir) -> Path:
    """Copy the bundled addon file into the target directory."""
    if not target.bundled_path.exists():
        raise FileNotFoundError(f"Bundled addon not found: {target.bundled_path}")

    if target.needs_subfolder:
        stem = Path(target.addon_filename).stem
        dest_dir = target.path / stem
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / target.addon_filename
    else:
        target.path.mkdir(parents=True, exist_ok=True)
        dest = target.path / target.addon_filename

    # Backup existing
    if dest.exists():
        try:
            shutil.copy2(dest, dest.with_suffix(dest.suffix + ".bak"))
        except OSError:
            pass

    shutil.copy2(target.bundled_path, dest)

    # Make executable on Linux/macOS (needed for GIMP plugins)
    if platform.system() != "Windows":
        import stat
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    target.installed_version = read_installed_version(dest)
    return dest


def uninstall_app_addon(target: AppAddonDir) -> bool:
    """Remove the addon file from the target directory."""
    addon = target.addon_file
    if addon.exists():
        try:
            addon.unlink()
            # Also remove the subfolder if empty (GIMP 3.0+)
            if target.needs_subfolder and addon.parent.is_dir():
                try:
                    addon.parent.rmdir()  # only removes if empty
                except OSError:
                    pass
            target.installed_version = ""
            return True
        except OSError:
            return False
    return False


def open_app_addon_dir(target: AppAddonDir) -> bool:
    """Open the addon directory in the OS file explorer."""
    target.path.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() == "Windows":
            import os
            os.startfile(str(target.path))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            import subprocess
            subprocess.Popen(["open", str(target.path)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(target.path)])
        return True
    except Exception:
        return False
