<h1 align="center">UNIFICATION</h1>

<p align="center">
  <img src="assets/logo.png" alt="UNIFICATION logo" width="140" />
</p>

<p align="center">
  <b>Vibe codez vos modeles 3D, images et plus encore</b><br/>
  Blender · FreeCAD · GIMP · Inkscape · Photoshop — 100&nbsp;% local, no API key, no cloud.<br/>
  Natural language prompt → Ollama → Python script → TCP MCP addon.
</p>

<p align="center">
  <a href="https://github.com/Oli97430/UNIFICATION/releases/latest">
    <img src="https://img.shields.io/github/v/release/Oli97430/UNIFICATION?display_name=tag&color=ff7a29" alt="Latest release"/>
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/blender-4.0%2B-orange" alt="Blender 4.0+"/>
  <img src="https://img.shields.io/badge/license-GPL--3.0-green" alt="GPL-3.0"/>
</p>

<p align="center">
  🇫🇷 <a href="README.fr.md">Version française</a>
</p>

---

## Table of contents

- [What it does](#what-it-does)
- [Features](#features)
- [Quick start](#quick-start)
- [Recommended models](#recommended-models)
- [Architecture](#architecture)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Settings](#settings)
- [User files](#user-files)
- [Troubleshooting](#troubleshooting)
- [Build & release](#build--release)
- [License](#license)

---

## What it does

UNIFICATION is a modern desktop client (built with `customtkinter`) that bridges a **local** Ollama LLM to multiple creative applications: **Blender · FreeCAD · GIMP · Inkscape · Photoshop**. You describe what you want in plain language; the app asks Ollama to write the Python script, then executes it inside your creative app over a TCP socket — all without a single byte leaving your machine.

| | |
|---|---|
| **No cloud** | Every token stays local. No quotas, no billing, no data leaks. |
| **One-click addon install** | The app detects every Blender installation on your system and copies the addon for you. |
| **Auto-fix on error** | When Blender raises an exception, the traceback is fed back to the model for a silent self-correction. |
| **Blender 4.x hardened** | Hardened system prompt + runtime AST sanitizer that rewrites broken API calls before they hit Blender (BSDF socket renames, removed lamp types, `brushes.new()` signature change, OBJ import/export, `mathutils.radians`, …). |
| **Vision support** | Attach a reference image when using a vision-capable model (`qwen2.5-vl`, `llava`, …). |
| **Multilingual** | Full English / French UI — auto-detected from your OS locale. |

---

## Features

### Setup & onboarding
- **Integrated addon installer** — auto-detects Blender data folders on Windows, macOS, Linux (including Snap and Flatpak). Downloads the latest release from GitHub; falls back to the bundled copy offline.
- **Model manager** — list, switch, and `ollama pull` with a live progress bar and cancel button, straight from the app.
- **Live status pills** for Ollama and Blender (click to force a refresh).
- **Silent update check** at startup — toast notification if a newer release exists on GitHub.

### Chat & code generation
- **Token-by-token streaming** with a Stop button and `Esc` shortcut.
- **Editable code** — tweak the generated script before sending it to Blender.
- **Auto-run** toggle — execute immediately after streaming completes.
- **Auto-fix loop** — on Blender error, automatically re-prompt with the traceback (configurable; 1 attempt by default).
- **AST lint** before send — syntax errors are caught without a Blender round-trip.
- **Render preview** — after execution, the addon renders the viewport and the app displays the PNG inline.
- **Per-turn stats** — token count, elapsed time, tokens/s.
- **Save `.py`** per turn; **export** the entire conversation as JSON.
- **Regenerate** (`↻`), **edit & resubmit** (`✎`), **copy** (`📋`) and **delete** (`🗑`) per turn.
- **Collapsible turns** — click any response header to collapse/expand.
- **Persistent history** across sessions (`~/.unification/history.json`), with automatic token-budget trimming.
- **Token budget indicator** — shows live `used / budget tok` near the prompt.
- **Dynamic prompt routing** — short read-only system prompt for inspection queries, full creator prompt for build requests.
- **Scene context injection** — queries Blender for the current object list before each prompt, so the model knows what exists.
- **Syntax highlighting** via Pygments, rendered inline in the turn card.
- **Timestamp & prompt mode badge** on every turn.

### Blender reliability layer
- **Automatic `temp_override` wrap** — every script runs inside a full `VIEW_3D` context override (window + screen + area + region + scene + view_layer). No more `Operator … context is incorrect` errors.
- **Best-effort OBJECT mode reset** before execution — prevents stale edit-mode from breaking operator polls.
- **Serialized execution queue** — concurrent Run clicks are serialized so they don't race on the TCP port.
- **TCP retry with exponential backoff** — 3 attempts on `ConnectionRefusedError` (1s → 2s → 4s).
- **Runtime AST sanitizer** — transparently rewrites known Blender 4.x API breakages:
  - `bpy.data.brushes.new(..., tool=X)` → strips `tool=`, appends `brush.sculpt_tool = X`
  - `tool='SCULPT'` used instead of `mode=` → renames the kwarg
  - Missing `mode=` → injects `mode='SCULPT'` as a safe default
  - `bpy.ops.export_scene.obj(...)` → `bpy.ops.wm.obj_export(...)` (removed in 4.0)
  - `bpy.ops.import_scene.obj(...)` → `bpy.ops.wm.obj_import(...)` (removed in 4.0)
  - `light_add(type='HEMI')` → `type='AREA'` (HEMI removed)
  - `nodes["Principled BSDF"]` → type-based lookup (locale-independent)
  - `mathutils.radians(...)` / `mathutils.degrees(...)` → `math.radians(...)` / `math.degrees(...)`
  - Auto-injects `import bpy` and `import math` when missing

---

## Quick start

### Option A — Windows executable (no Python required)

1. Download `UNIFICATION.exe` from the latest [GitHub Release](https://github.com/Oli97430/UNIFICATION/releases/latest).
2. Double-click. No installer, no virtual environment.

### Option B — Run from source (Windows / macOS / Linux)

```bash
git clone https://github.com/Oli97430/UNIFICATION.git
cd UNIFICATION
```

**Windows:**
```bat
run.bat
```

**macOS / Linux:**
```bash
chmod +x run.sh && ./run.sh
```

Both scripts create a virtual environment, install dependencies, and launch the app. Manual equivalent:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### First run checklist

1. **Setup tab** → select your Blender installation → click **Install / Update addon**.
2. Start Ollama: `ollama serve` (auto-started on Windows and macOS).
3. **Models tab** → select `qwen2.5-coder:7b` → click **Pull model** (~4.7 GB).  
   Or via CLI: `ollama pull qwen2.5-coder:7b`
4. **In Blender**: Edit → Preferences → Add-ons → search "MCP Server" → enable it. Start the server from the N-Panel in the 3D Viewport.
5. Back in the app, both status pills (Ollama, Blender) should turn green.
6. Type a request in the Chat tab and press `Ctrl+Enter`.

---

## Recommended models

> **Q4_K_M** — 4-bit K-means quantization, medium size. The default quality/VRAM sweet spot for code models.

| Model | VRAM | Notes |
|---|---|---|
| `qwen2.5:32b` | ~20 GB | **Default** — best overall quality for `bpy` code |
| `qwen2.5-coder:7b` | ~5 GB | Best compact model for code |
| `qwen2.5-coder:14b` | ~9 GB | Sharper on complex multi-step tasks |
| `qwen2.5-coder:3b` | ~2 GB | Lightweight GPU or CPU-only |
| `deepseek-coder-v2:16b` | ~9 GB | Strong alternative |
| `codellama:13b` | ~7 GB | The classic |
| `llama3.1:8b` | ~5 GB | General-purpose |
| `qwen2.5-vl:7b` *(vision)* | ~6 GB | Attach images to the prompt |
| `qwen2.5-vl:32b` *(vision)* | ~20 GB | Best vision model for 24 GB VRAM users |
| `llava:7b` *(vision)* | ~5 GB | Alternative vision model |

---

## Architecture

```
┌─────────────────────┐  prompt   ┌───────────┐  bpy script  ┌─────────────────────┐
│  UNIFICATION    │ ────────► │  Ollama   │ ──────────►  │  blender-mcp-addon  │
│     (this app)      │ ◄──────── │  (local)  │              │    (port 9876)      │
└─────────────────────┘  tokens   └───────────┘              └─────────────────────┘
          ▲                                                           │
          └────────── stdout / result / render PNG / error  ◄─────────┘
```

| Module | Role |
|---|---|
| `core/ollama_client.py` | HTTP streaming client (`/api/chat`, `/api/tags`, `/api/pull`), token budget, vision detection |
| `core/blender_client.py` | TCP client, `temp_override` wrap, render postamble, AST sanitizer (7 rewrite rules) |
| `core/system_prompt.py` | Creator & query prompts, Blender 4.x rules, intent router |
| `core/lint.py` | Pre-flight `ast.parse` lint + semantic pattern warnings |
| `core/addon_installer.py` | Multi-OS Blender folder detection, GitHub download, offline fallback |
| `core/updater.py` | GitHub Releases update check |
| `core/i18n.py` | EN / FR translation table, auto OS-locale detection |
| `core/settings.py` | JSON settings persistence |
| `gui/app.py` | Main window — sidebar with Chat / Setup / Models / Settings / Logs / About tabs |
| `gui/chat_turn.py` | Turn card — streaming dot animation, editable CodeView, collapsible, stats, inline preview |
| `gui/widgets.py` | `CodeView` (Pygments), `StatusPill`, `Toast`, `Tooltip`, `InlineImage`, `IconButton` |
| `gui/theme.py` | Design tokens (colors, fonts, radii, scales) |
| `assets/blender_mcp_addon.py` | Offline-bundled addon |

---

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Send prompt | `Ctrl+Enter` |
| Stop streaming | `Esc` |
| Clear conversation | `Ctrl+L` |
| Focus prompt input | `Ctrl+K` |
| Open Settings | `Ctrl+,` |
| Switch to Chat / Setup / Models / Logs | `Ctrl+1` / `Ctrl+2` / `Ctrl+3` / `Ctrl+4` |

---

## Settings

All settings live in the **Settings tab**:

| Section | Options |
|---|---|
| Ollama | Endpoint URL, temperature, keep-alive duration |
| Blender | Host, port, "Test connection" |
| Behaviour | Persist history, auto-route prompt, scene context injection, check for updates, context window (num_ctx), max history tokens, auto-fix attempts |
| Appearance | Dark / light / system theme, language (Auto / English / Français) |

Inline toggles in the chat bar:

| Toggle | Effect |
|---|---|
| **Auto-run** | Execute code immediately after streaming |
| **Auto-fix** | Re-submit to the model on Blender error |
| **Preview** | Render the viewport after execution |

---

## User files

Everything lives under `~/.unification/` — no registry, no hidden folders elsewhere.

```
~/.unification/
├── settings.json     # persistent app settings
├── history.json      # conversation history (if enabled)
└── events.log        # event log (visible in the Logs tab)
```

No telemetry. No network calls except to your local Ollama instance and GitHub's release API (update check, opt-out in Settings).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Ollama** pill stays red | Run `ollama serve`, or check the URL in Settings. |
| **Blender** pill stays red | The addon isn't started. Go to Setup tab → Install. Then enable it in Blender: Edit → Preferences → Add-ons → "MCP Server". |
| `Operator … context is incorrect` | Should be auto-handled by the VIEW_3D wrap. If it persists, check the Logs tab for details. |
| `KeyError: 'Principled BSDF'` | Regenerate the turn (`↻`). The system prompt teaches the robust BSDF lookup pattern. |
| `TypeError: brushes.new() tool=…` | Fixed automatically by the runtime AST sanitizer since v1.1.2. Update the app if you see this. |
| `import_scene.obj` / `export_scene.obj` not found | Fixed automatically — the sanitizer rewrites to `wm.obj_import` / `wm.obj_export`. |
| `mathutils.radians` / `mathutils.degrees` | Fixed automatically — rewritten to `math.radians` / `math.degrees`. |
| Model hallucinates `bpy` calls | Use `qwen2.5-coder:7b` or `:14b`. Lower temperature to `0.1`. |
| App won't start | Run `python main.py` in a terminal to see the traceback. Check `pip install -r requirements.txt`. |
| Conversation too slow | Reduce **Max history tokens** in Settings or clear with `Ctrl+L`. |

---

## Build & release

### Build the Windows exe

```bat
build.bat
```

Produces `dist\UNIFICATION.exe` (single-file, windowed, custom icon). On macOS / Linux:

```bash
./build.sh
```

### Publish a release

```bash
git tag -a v1.x.y -m "vX.Y.Z — description"
git push origin main && git push origin v1.x.y

gh release create v1.x.y dist/UNIFICATION.exe \
    --title "vX.Y.Z — Short description" \
    --notes "Changelog here"
```

The in-app update checker queries `https://api.github.com/repos/Oli97430/UNIFICATION/releases/latest` and compares `tag_name` against `APP_VERSION` in `gui/app.py`. If a newer release exists, a toast appears with a link to the release page.

---

## License

[GPL-3.0-or-later](LICENSE) — to stay compatible with the blender-mcp-addon and the upstream Blender ecosystem.
