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
- [Creative app setup](#creative-app-setup)
- [MCP Server for Claude Desktop / Cursor](#mcp-server-for-claude-desktop--cursor)
- [Recommended models](#recommended-models)
- [Architecture](#architecture)
- [TCP protocol](#tcp-protocol)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Settings](#settings)
- [User files](#user-files)
- [Troubleshooting](#troubleshooting)
- [Build & release](#build--release)
- [License](#license)

---

## What it does

UNIFICATION is a modern desktop client (built with `customtkinter`) that bridges a **local** Ollama LLM to **five creative applications**:

| App | Port | Addon type | What you can do |
|---|---|---|---|
| **Blender** | 9876 | Built-in addon (N-Panel) | Model, animate, render, sculpt, shade — full `bpy` API |
| **FreeCAD** | 9877 | Macro plugin | Parametric CAD, Part/Draft/Sketch scripting |
| **GIMP** | 9878 | Python-Fu plugin | Image editing, filters, batch processing |
| **Inkscape** | 9879 | Standalone server | SVG manipulation via lxml/inkex + Inkscape CLI |
| **Photoshop** | 9880 | Standalone server | COM automation (Win) / AppleScript (macOS) + ExtendScript |

You describe what you want in plain language; the app asks Ollama to write the Python script, then executes it inside your creative app over a TCP socket — **all without a single byte leaving your machine**.

| | |
|---|---|
| **No cloud** | Every token stays local. No quotas, no billing, no data leaks. |
| **One-click addon install** | The app detects every Blender installation on your system and copies the addon for you. |
| **Auto-fix on error** | When Blender raises an exception, the traceback is fed back to the model for silent self-correction. |
| **Blender 4.x hardened** | Hardened system prompt + runtime AST sanitizer with **8 rewrite rules** that fix broken API calls before they hit Blender. |
| **Category-aware prompts** | 10 Blender categories (materials, lighting, physics, particles, sculpting, rendering, geometry nodes, modeling, animation, import/export) detected from your prompt — only relevant API docs are injected. |
| **Visual prompt badges** | Colored pills on each chat turn show the prompt mode (creator / query / fix) and detected categories at a glance. |
| **Multi-LLM providers** | Ollama (default, local), plus optional Claude, OpenAI, and Gemini backends — same streaming interface, no vendor SDK required. |
| **Vision support** | Attach a reference image when using a vision-capable model (`qwen2.5-vl`, `llava`, …). |
| **Multilingual** | Full English / French UI — auto-detected from your OS locale. |
| **MCP Server** | Unified stdio JSON-RPC 2.0 server for Claude Desktop / Cursor — controls all 5 apps from one endpoint. |

---

## Features

### Setup & onboarding
- **Integrated Blender addon installer** — auto-detects Blender data folders on Windows, macOS, Linux (including Snap and Flatpak). Downloads the latest release from GitHub; falls back to the bundled copy offline.
- **Model manager** — list, switch, and `ollama pull` with a live progress bar and cancel button, straight from the app.
- **Live status pills** for Ollama + all 5 creative apps (click to force a refresh). Parallel TCP pings — all checked simultaneously.
- **Silent update check** at startup — toast notification if a newer release exists on GitHub.

### Chat & code generation
- **Token-by-token streaming** with a Stop button and `Esc` shortcut.
- **Editable code** — tweak the generated script before sending it to Blender.
- **Auto-run** toggle — execute immediately after streaming completes.
- **Auto-fix loop** — on Blender error, automatically re-prompt with the traceback (configurable; 1 attempt by default).
- **AST lint** before send — syntax errors are caught without a Blender round-trip.
- **Render preview** — after execution, the addon renders the viewport and the app displays the PNG inline.
- **Per-turn stats** — prompt/response token count, elapsed time, tokens/s.
- **Save `.py`** per turn; **export** the entire conversation as JSON.
- **Regenerate** (`↻`), **edit & resubmit** (`✎`), **copy** (`📋`) and **delete** (`🗑`) per turn.
- **Collapsible turns** — click any response header to collapse/expand.
- **Persistent history** across sessions (`~/.unification/history.json`), with automatic token-budget trimming.
- **Token budget indicator** — shows live `used / budget tok` near the prompt.
- **Dynamic prompt routing** — short read-only system prompt for inspection queries (keywords: "list", "show", "count", "how many"…), full creator prompt for build requests.
- **Scene context injection** — queries Blender for the current object list before each prompt, so the model knows what exists.
- **Syntax highlighting** via Pygments, rendered inline in the turn card.
- **Timestamp & prompt mode badge** on every turn.
- **Vision model support** — attach images when using `qwen2.5-vl`, `llava`, `moondream`, `minicpm-v`, etc. Detected automatically from the model name.

### Blender reliability layer
- **Automatic `temp_override` wrap** — every script runs inside a full `VIEW_3D` context override (window + screen + area + region + scene + view_layer). No more `Operator … context is incorrect` errors.
- **Best-effort OBJECT mode reset** before execution — prevents stale edit-mode from breaking operator polls.
- **Serialized execution queue** — concurrent Run clicks are serialized so they don't race on the TCP port.
- **TCP retry with exponential backoff** — 3 attempts on `ConnectionRefusedError` (1 s → 2 s → 4 s).
- **Runtime AST sanitizer** — transparently rewrites known Blender 4.x API breakages:

| # | What it catches | Rewrite |
|---|---|---|
| 1 | Missing `import bpy` / `import math` | Auto-injects at top |
| 2 | `bpy.ops.export_scene.obj(...)` | → `bpy.ops.wm.obj_export(...)` (removed in 4.0) |
| 3 | `bpy.ops.import_scene.obj(...)` | → `bpy.ops.wm.obj_import(...)` (removed in 4.0) |
| 4 | `light_add(type='HEMI')` | → `type='AREA'` (HEMI removed) |
| 5 | `nodes["Principled BSDF"]` | → type-based lookup `n.type == "BSDF_PRINCIPLED"` (locale-independent) |
| 6 | `mathutils.radians(...)` / `.degrees(...)` | → `math.radians(...)` / `math.degrees(...)` |
| 7 | `bpy.data.brushes.new(..., tool=X)` | AST rewrite: strips `tool=`, adds `brush.sculpt_tool = X`, fixes `tool=` → `mode=` kwarg |
| 8 | `subdivision_set(levels=N)` | → `subdivision_set(level=N)` (Blender expects `level`, singular) |

---

## Quick start

### Option A — Windows executable (no Python required)

1. Download `Unification.exe` from the latest [GitHub Release](https://github.com/Oli97430/UNIFICATION/releases/latest).
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

### Dependencies

```
customtkinter>=5.2.2
Pillow>=10.0.0
Pygments>=2.17.0
requests>=2.31.0
```

No paid API SDKs — everything runs through local Ollama.

### First run checklist

1. **Setup tab** → select your Blender installation → click **Install / Update addon**.
2. Start Ollama: `ollama serve` (auto-started on Windows and macOS).
3. **Models tab** → select `qwen2.5-coder:7b` → click **Pull model** (~4.7 GB).  
   Or via CLI: `ollama pull qwen2.5-coder:7b`
4. **In Blender**: Edit → Preferences → Add-ons → search "MCP Server" → enable it. Start the server from the N-Panel in the 3D Viewport.
5. Back in the app, both status pills (Ollama, Blender) should turn green.
6. Type a request in the Chat tab and press `Ctrl+Enter`.

---

## Creative app setup

Each creative app needs its MCP addon running to accept TCP commands from UNIFICATION. All addons share the same JSON + null-byte protocol.

### Blender (port 9876)

The Blender addon is installed automatically via the **Setup tab**. Alternatively:

1. Copy `assets/blender_mcp_addon.py` to your Blender addons folder:
   - **Windows:** `%USERPROFILE%\AppData\Roaming\Blender Foundation\Blender\<X.Y>\scripts\addons\`
   - **macOS:** `~/Library/Application Support/Blender/<X.Y>/scripts/addons/`
   - **Linux:** `~/.config/blender/<X.Y>/scripts/addons/`
2. In Blender: Edit → Preferences → Add-ons → search "MCP Server" → enable.
3. 3D Viewport → N-Panel → MCP tab → **Start Server**.

The status pill turns green when connected.

### FreeCAD (port 9877)

1. Copy `assets/freecad_mcp_addon.py` to the FreeCAD Macro folder:
   - **Windows:** `%APPDATA%\FreeCAD\Macro\`
   - **macOS:** `~/Library/Application Support/FreeCAD/Macro/`
   - **Linux:** `~/.local/share/FreeCAD/Macro/`
2. In FreeCAD: Macro → Macros → select `freecad_mcp_addon` → **Execute**.
3. Or from the Python console: `exec(open("path/to/freecad_mcp_addon.py").read())`
4. To stop: `from freecad_mcp_addon import server_stop; server_stop()`

### GIMP (port 9878)

**GIMP 2.10:**
1. Copy `assets/gimp_mcp_addon.py` to the plug-ins folder:
   - **Windows:** `%APPDATA%\GIMP\2.10\plug-ins\`
   - **macOS:** `~/Library/Application Support/GIMP/2.10/plug-ins/`
   - **Linux:** `~/.config/GIMP/2.10/plug-ins/` (must be `chmod +x`)
2. Restart GIMP.
3. Filters → Python-Fu → **MCP Server Start**.

**GIMP 3.0+ (tested on 3.2):**
1. Create a subfolder matching the script name:
   - **Windows:** `%APPDATA%\GIMP\3.2\plug-ins\gimp_mcp_addon\`
   - **macOS:** `~/Library/Application Support/GIMP/3.2/plug-ins/gimp_mcp_addon/`
   - **Linux:** `~/.config/GIMP/3.2/plug-ins/gimp_mcp_addon/`
2. Copy `gimp_mcp_addon.py` inside that subfolder.
3. Restart GIMP.
4. Open or create an image, then Filters → **MCP Server Start**.

> **Note:** GIMP 3 kills plugin subprocesses after execution, so the addon spawns a **detached standalone Python process** that survives independently. The menu item "MCP Server Stop" terminates it.

### Inkscape (port 9879)

Inkscape doesn't support persistent plugins, so this addon runs as a **standalone server** alongside Inkscape:

```bash
pip install lxml            # required
pip install inkex            # optional, for inkex helpers
python assets/inkscape_mcp_server.py --port 9879
```

The server executes Python code with `lxml.etree`, `lxml.builder`, `inkex` (if available) pre-loaded, and can invoke the Inkscape CLI for rendering and export.

### Photoshop (port 9880)

The Photoshop addon also runs as a **standalone server** that controls Photoshop via COM (Windows) or AppleScript (macOS):

**Windows:**
```bash
pip install pywin32
python assets/photoshop_mcp_server.py --port 9880
```

**macOS:**
```bash
python assets/photoshop_mcp_server.py --port 9880
```

The server provides a pre-loaded `ps` object (the Photoshop COM/AppleScript bridge) and supports `DoJavaScript()` for ExtendScript execution.

---

## MCP Server for Claude Desktop / Cursor

UNIFICATION ships a **unified MCP server** (`mcp_server.py`) that exposes all 5 creative apps to Claude Desktop, Cursor, or any MCP-compatible client over stdio JSON-RPC 2.0.

### Setup

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "creative-suite": {
      "command": "python",
      "args": ["C:/path/to/UNIFICATION/mcp_server.py"]
    }
  }
}
```

### Exposed tools

| Tool | Description |
|---|---|
| `execute_blender_code` | Send Python (`bpy`) code to Blender on port 9876 |
| `execute_freecad_code` | Send Python (FreeCAD/Part/Draft) code to FreeCAD on port 9877 |
| `execute_gimp_code` | Send Python-Fu code to GIMP on port 9878 |
| `execute_inkscape_code` | Send Python (lxml/inkex) code to Inkscape on port 9879 |
| `execute_photoshop_code` | Send Python/ExtendScript code to Photoshop on port 9880 |
| `ping_all` | Check connectivity to all 5 apps at once |
| `get_app_status` | Get scene/document info from a specific app |

### Testing

```bash
python mcp_server.py --test     # check connectivity to all apps
python mcp_server.py --help     # show documentation
```

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

Vision models are auto-detected from the model name (markers: `vl`, `llava`, `vision`, `moondream`, `minicpm-v`). When detected, the image attachment button appears in the chat bar.

---

## Architecture

```
                                    ┌─────────────────────────────────────────────────┐
                                    │            Creative Applications                │
┌──────────────────┐   prompt       │                                                 │
│   UNIFICATION    │ ──────────►    │  ┌──────────┐  Blender    (bpy)     port 9876   │
│   (this app)     │   ┌────────┐   │  ├──────────┤  FreeCAD    (Part)    port 9877   │
│                  │──►│ Ollama │──►│  ├──────────┤  GIMP       (Py-Fu)   port 9878   │
│  customtkinter   │◄──│(local) │   │  ├──────────┤  Inkscape   (lxml)    port 9879   │
│  GUI + 6 tabs    │   └────────┘   │  └──────────┘  Photoshop  (COM/AS)  port 9880   │
└──────────────────┘   tokens       └─────────────────────────────────────────────────┘
         ▲                                           │
         └────── stdout / result / render PNG ◄──────┘
```

```
┌─────────────────────────────────┐          ┌─────────────────────────────────┐
│  Claude Desktop / Cursor        │  stdio   │         mcp_server.py           │
│  (or any MCP client)            │◄────────►│  JSON-RPC 2.0  ·  7 tools      │
└─────────────────────────────────┘          │  → routes to ports 9876-9880    │
                                             └─────────────────────────────────┘
```

### Modules

| Module | Role |
|---|---|
| `main.py` | Entry point — adds project root to `sys.path`, calls `gui.app.main()` |
| `core/ollama_client.py` | HTTP streaming client (`/api/chat`, `/api/tags`), token budget, vision detection, code extraction |
| `core/blender_client.py` | TCP client, `temp_override` wrap, render postamble, AST sanitizer (8 rewrite rules), exponential backoff retry |
| `core/tcp_ping.py` | Lightweight TCP ping for FreeCAD / GIMP / Inkscape / Photoshop addons |
| `core/system_prompt.py` | Creator & query prompts, Blender 4.x rules, 10-category keyword detection, intent router (`is_query_intent`) |
| `core/lint.py` | Pre-flight `ast.parse` lint + 5 semantic pattern warnings |
| `core/addon_installer.py` | Multi-OS Blender folder detection (Win/macOS/Linux/Snap/Flatpak), GitHub download, offline fallback |
| `core/updater.py` | GitHub Releases update check (`tag_name` vs `APP_VERSION`) |
| `core/i18n.py` | EN / FR translation table (~200 keys), auto OS-locale detection, `t(key)` API |
| `core/settings.py` | JSON settings persistence to `~/.unification/settings.json` (20+ fields) |
| `gui/app.py` | Main window — sidebar with Chat / Setup / Models / Settings / Logs / About tabs, 6 status pills, model selector |
| `gui/chat_turn.py` | Turn card — streaming dot animation, editable CodeView, collapsible, per-turn stats, inline render preview |
| `gui/widgets.py` | `CodeView` (Pygments), `StatusPill`, `Toast`, `Tooltip`, `InlineImage`, `IconButton` |
| `gui/theme.py` | Design tokens (colors, fonts, radii, scales) — dark/light/system |
| `mcp_server.py` | Unified MCP server (stdio JSON-RPC 2.0) — 7 tools, routes to all 5 creative apps |
| `assets/blender_mcp_addon.py` | Blender N-Panel addon — TCP server on port 9876, background thread, main-thread exec queue |
| `assets/freecad_mcp_addon.py` | FreeCAD Macro plugin — TCP server on port 9877 |
| `core/llm_providers.py` | Unified streaming LLM providers — Ollama (local), Claude, OpenAI, Gemini — same `chat_stream()` interface |
| `assets/gimp_mcp_addon.py` | GIMP 2.x/3.x plugin — TCP server on port 9878 (GIMP 3: detached standalone process) |
| `assets/inkscape_mcp_server.py` | Standalone server for Inkscape — TCP on port 9879, lxml/inkex + CLI |
| `assets/photoshop_mcp_server.py` | Standalone server for Photoshop — TCP on port 9880, COM (Win) / AppleScript (macOS) |

---

## TCP protocol

All 5 addons share the same framing: **JSON + null byte (`\0`) delimiter** over raw TCP.

### Request

```json
{"type": "execute", "code": "import bpy\nbpy.ops.mesh.primitive_cube_add()"}
```

Followed by a `\0` byte.

### Response

```json
{"status": "ok", "result": "Cube created", "stdout": "..."}
```

Or on error:

```json
{"status": "error", "message": "Traceback (most recent call last):\n  ..."}
```

### Ports

| Port | Application |
|---|---|
| 9876 | Blender |
| 9877 | FreeCAD |
| 9878 | GIMP |
| 9879 | Inkscape |
| 9880 | Photoshop |

All bind to `127.0.0.1` (localhost only). Default timeout: 30 seconds.

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

All settings live in the **Settings tab** and persist to `~/.unification/settings.json`:

| Section | Option | Default | Description |
|---|---|---|---|
| **Ollama** | Endpoint URL | `http://localhost:11434` | Ollama API base URL |
| | Temperature | `0.2` | Lower = more deterministic |
| | Keep-alive | `5m` | How long Ollama keeps the model in memory |
| **Blender** | Host | `127.0.0.1` | TCP host for all addons |
| | Port | `9876` | Blender addon port |
| | Test connection | — | Manual ping button |
| **Behaviour** | Persist history | `true` | Save conversation to `history.json` |
| | Auto-route prompt | `true` | Short prompt for queries, full prompt for builds |
| | Scene context injection | `true` | Query Blender for object list before each prompt |
| | Check for updates | `true` | Silent GitHub Releases check at startup |
| | Context window (num_ctx) | `8192` | Ollama context window size |
| | Max history tokens | `8000` | Token budget for conversation history |
| | Auto-fix attempts | `1` | Max re-prompts on error (0 = disabled) |
| **Appearance** | Theme | `dark` | Dark / Light / System |
| | Language | `auto` | Auto (OS locale) / English / Français |

Inline toggles in the chat bar:

| Toggle | Default | Effect |
|---|---|---|
| **Auto-run** | on | Execute code immediately after streaming |
| **Auto-fix** | on | Re-submit to the model on Blender error |
| **Preview** | off | Render the viewport after execution |

---

## User files

Everything lives under `~/.unification/` — no registry, no hidden folders elsewhere.

```
~/.unification/
├── settings.json     # persistent app settings (20+ fields)
├── history.json      # conversation history (if enabled)
└── events.log        # event log (visible in the Logs tab)
```

No telemetry. No network calls except to your local Ollama instance and GitHub's release API (update check, opt-out in Settings).

---

## Troubleshooting

### General

| Symptom | Fix |
|---|---|
| App won't start | Run `python main.py` in a terminal to see the traceback. Check `pip install -r requirements.txt`. |
| Model hallucinates `bpy` calls | Use `qwen2.5-coder:7b` or `:14b`. Lower temperature to `0.1`. |
| Conversation too slow | Reduce **Max history tokens** in Settings or clear with `Ctrl+L`. |

### Ollama

| Symptom | Fix |
|---|---|
| **Ollama** pill stays red | Run `ollama serve`, or check the URL in Settings. |

### Blender

| Symptom | Fix |
|---|---|
| **Blender** pill stays red | The addon isn't started. Go to Setup tab → Install. Then in Blender: Edit → Preferences → Add-ons → "MCP Server" → Enable. N-Panel → MCP → Start Server. |
| `Operator … context is incorrect` | Should be auto-handled by the VIEW_3D wrap. If it persists, check the Logs tab. |
| `KeyError: 'Principled BSDF'` | Regenerate the turn (`↻`). The system prompt teaches the robust BSDF lookup pattern. The sanitizer also auto-fixes this. |
| `TypeError: brushes.new() tool=…` | Fixed by the runtime AST sanitizer since v1.1.2. Update the app. |
| `import_scene.obj` / `export_scene.obj` not found | Fixed automatically — the sanitizer rewrites to `wm.obj_import` / `wm.obj_export`. |
| `mathutils.radians` / `mathutils.degrees` | Fixed automatically — rewritten to `math.radians` / `math.degrees`. |
| `subdivision_set(levels=N)` | Fixed automatically — rewritten to `level` (singular). |
| `NameError: name 'size' is not defined` | Regenerate (`↻`). The system prompt now enforces defining all variables before use. |

### FreeCAD

| Symptom | Fix |
|---|---|
| **FreeCAD** pill stays red | Make sure the macro is running. In FreeCAD: Macro → Macros → `freecad_mcp_addon` → Execute. |
| Macro not found | Copy `assets/freecad_mcp_addon.py` to `%APPDATA%\FreeCAD\Macro\` (Windows) or `~/.local/share/FreeCAD/Macro/` (Linux). |

### GIMP

| Symptom | Fix |
|---|---|
| **GIMP** pill stays red | Open an image first, then Filters → MCP Server Start. GIMP 3 requires an open image for the menu item to be active. |
| Plugin not visible in menus | GIMP 2.10: check file permissions (`chmod +x` on Linux/macOS). GIMP 3.0+: the script must be in a subfolder with the same name (`gimp_mcp_addon/gimp_mcp_addon.py`). |
| Server started but ping fails | GIMP 3 spawns a detached Python process. Check if it's running (`gimp_mcp_server.pid` in your temp folder). Try Filters → MCP Server Stop, then Start again. |

### Inkscape

| Symptom | Fix |
|---|---|
| **Inkscape** pill stays red | The standalone server isn't running. Run `python assets/inkscape_mcp_server.py`. |
| `lxml` not found | `pip install lxml` — required for the Inkscape server. |

### Photoshop

| Symptom | Fix |
|---|---|
| **Photoshop** pill stays red | The standalone server isn't running. Run `python assets/photoshop_mcp_server.py`. |
| COM error (Windows) | `pip install pywin32`. Make sure Photoshop is open. |
| AppleScript error (macOS) | Grant Terminal / Python automation access in System Settings → Privacy & Security. |

---

## Build & release

### Build the Windows exe

```bat
build.bat
```

Produces `dist\Unification.exe` (single-file, windowed, custom icon, ~21 MB). On macOS / Linux:

```bash
./build.sh
```

The build bundles: all addon files (Blender, FreeCAD, GIMP, Inkscape, Photoshop), `mcp_server.py`, logo assets, and customtkinter theme data.

### Regenerate the logo

```bash
python assets/make_logo.py
```

Generates `logo.png` (512 px), `logo_128.png`, `logo_64.png`, `logo_32.png`, and `logo.ico` (multi-size). The logo is an Einstein side-profile silhouette — a nod to the unified field theory that inspired the app name.

### Publish a release

```bash
git tag -a v2.x.y -m "v2.x.y — description"
git push origin main && git push origin v2.x.y

gh release create v2.x.y dist/Unification.exe \
    --title "v2.x.y — Short description" \
    --notes "Changelog here"
```

The in-app update checker queries `https://api.github.com/repos/Oli97430/UNIFICATION/releases/latest` and compares `tag_name` against `APP_VERSION` in `gui/app.py`. If a newer release exists, a toast appears with a link to the release page.

---

## License

[GPL-3.0-or-later](LICENSE) — to stay compatible with the blender-mcp-addon and the upstream Blender ecosystem.
