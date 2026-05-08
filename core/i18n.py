"""Tiny i18n layer used across the GUI.

Usage
-----
    from core.i18n import t, set_language, available_languages

    label = t("sidebar.chat")        # "Chat" / "Discussion"
    msg   = t("toast.exported")      # "Exported" / "Exporté"
    msg   = t("toast.pulled", name="qwen2.5-coder:7b")  # f-string-style

Languages
---------
- "en" — base / fallback. Every key MUST exist in `TRANSLATIONS["en"]`.
- "fr" — French.
- "auto" (in settings) — follow the OS locale, fall back to "en".

If a key is missing from a language, the English string is used; if it is also
missing from English, the key itself is returned (so missing keys show up
visibly during development without crashing the UI).
"""
from __future__ import annotations

import locale
from typing import Iterable


# ---------------------------------------------------------------- tables


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # --- window chrome
        "app.subtitle": "   ·  Vibe codez vos modeles 3D, images et plus encore",
        "header.update.available": "Update available: {version}  ·  click About",
        "header.update.no_network": "",

        # --- sidebar
        "sidebar.chat": "Chat",
        "sidebar.setup": "Setup",
        "sidebar.models": "Models",
        "sidebar.settings": "Settings",
        "sidebar.logs": "Logs",
        "sidebar.about": "About",
        "sidebar.model_label": "MODEL",
        "sidebar.model_tooltip": "Active Ollama model — change anytime",

        # --- pills
        "pill.ollama": "Ollama",
        "pill.ollama.offline": "Ollama offline",
        "pill.ollama.tooltip": "Click to refresh status",
        "pill.blender": "Blender",
        "pill.blender.offline": "Blender offline",
        "pill.blender.tooltip": "Click to ping the Blender addon",
        "pill.freecad": "FreeCAD",
        "pill.freecad.offline": "FreeCAD offline",
        "pill.freecad.tooltip": "Click to ping the FreeCAD addon",
        "pill.gimp": "GIMP",
        "pill.gimp.offline": "GIMP offline",
        "pill.gimp.tooltip": "Click to ping the GIMP addon",
        "pill.inkscape": "Inkscape",
        "pill.inkscape.offline": "Inkscape offline",
        "pill.inkscape.tooltip": "Click to ping the Inkscape server",
        "pill.photoshop": "Photoshop",
        "pill.photoshop.offline": "Photoshop offline",
        "pill.photoshop.tooltip": "Click to ping the Photoshop server",

        # --- chat / empty state
        "chat.empty.title": "UNIFICATION",
        "chat.empty.subtitle": "Describe what you want to create.\nOllama generates the code, the addon runs it in your creative app.",
        "chat.placeholder": "Describe a task…   (e.g. add a glass sphere in Blender, draw a red circle in Inkscape)",
        "chat.hint.send": "Ctrl+Enter to send",

        "chat.btn.auto_run": "Auto-run",
        "chat.btn.auto_run.tooltip": "Run the generated code immediately after streaming ends",
        "chat.btn.auto_fix": "Auto-fix",
        "chat.btn.auto_fix.tooltip": "If Blender returns an error, ask the model to fix it automatically",
        "chat.btn.preview": "Preview",
        "chat.btn.preview.tooltip": "Render a viewport preview after each run and show it inline",
        "chat.btn.send": "Send  ⏎",
        "chat.btn.send.tooltip": "Send (Ctrl+Enter)",
        "chat.btn.clear": "Clear",
        "chat.btn.clear.tooltip": "Clear all turns  (Ctrl+L)",
        "chat.btn.export": "Export",
        "chat.btn.export.tooltip": "Save the whole conversation as JSON",
        "chat.btn.attach.tooltip": "Attach an image (vision-capable models only)",
        "chat.attach.remove": "✕  remove",
        "chat.attach.remove.tooltip": "Remove this attachment",

        # --- chat turn
        "turn.assistant": "  Assistant",
        "turn.thinking": "thinking…",
        "turn.streaming": "streaming…",
        "turn.ready": "ready",
        "turn.stopped": "stopped",
        "turn.error": "error",
        "turn.btn.run": "▶  Run in Blender",
        "turn.btn.run.prefix": "Run in",
        "turn.btn.run.tooltip": "Send the code to the target creative app",
        "turn.btn.run.running": "… running",
        "turn.btn.regenerate": "↻  Regenerate",
        "turn.btn.regenerate.tooltip": "Re-ask the model with the same prompt",
        "turn.btn.save_py": "Save .py",
        "code.copy": "Copy",
        "code.copied": "Copied",
        "code.save_title": "Save Python script",
        "code.lines": "{n} lines",
        "code.line": "{n} line",
        "turn.btn.save_py.tooltip": "Save the generated script to a .py file",
        "turn.btn.delete": "🗑",
        "turn.btn.delete.tooltip": "Remove this turn from the conversation",
        "turn.btn.stop": "■  Stop",
        "turn.btn.stop.tooltip": "Cancel the streaming response",
        "turn.result.ok": "✓  Executed in {app}",
        "turn.result.error": "✗  {app} raised an exception",
        "turn.result.transport_error": "✗  Cannot reach {app} — is the addon running?",
        "turn.result.empty": "(no output)",
        "turn.attach.caption": "attached image",
        "turn.preview.caption": "viewport preview",
        "turn.fix.attempt": "(auto-fix attempt {n})",

        # --- setup view
        "setup.title": "Setup",
        "setup.intro": (
            "Install MCP addons into your creative apps.  "
            "Each addon is a tiny TCP server that lets UNIFICATION send scripts remotely."
        ),
        "setup.detected.title": "Detected installs",
        "setup.bundled_version": "Bundled addon: v{version}",
        "setup.btn.refresh": "Refresh",
        "setup.no_install": (
            "No install detected automatically.\n"
            "Add a path manually below."
        ),
        "setup.no_install.blender": (
            "No Blender install detected automatically.\n"
            "Add a path manually below — typically:\n"
            "   %APPDATA%\\Blender Foundation\\Blender\\<X.Y>\\scripts\\addons"
        ),
        "setup.no_install.freecad": (
            "No FreeCAD detected automatically.\n"
            "Add a path manually — typically:\n"
            "   %APPDATA%\\FreeCAD\\Macro\\"
        ),
        "setup.no_install.gimp": (
            "No GIMP detected automatically.\n"
            "Add a path manually — typically:\n"
            "   %APPDATA%\\GIMP\\2.10\\plug-ins\\"
        ),
        "setup.custom_path": "Custom path",
        "setup.btn.browse": "Browse",
        "setup.btn.browse.tooltip": "Pick an addon directory",
        "setup.btn.use": "Use",
        "setup.btn.use.tooltip": "Add this folder to the list",
        "setup.source.title": "Install source",
        "setup.source.remote": "Latest from GitHub",
        "setup.source.bundled": "Bundled (offline)",
        "setup.source.bundled.tooltip": "Use the .py shipped inside this app",
        "setup.btn.install": "⬇  Install / Update addon",
        "setup.btn.reinstall": "⟳  Reinstall / update",
        "setup.btn.install_only": "⬇  Install addon",
        "setup.btn.open_folder": "📂  Open folder",
        "setup.btn.open_folder.tooltip": "Reveal the addons folder in your file explorer",
        "setup.btn.uninstall": "🗑  Uninstall",
        "setup.btn.uninstall.tooltip": "Remove the addon from the selected directory",
        "setup.status.select": "Select a directory above.",
        "setup.status.installed": "v{version} installed in:\n{path}",
        "setup.status.will_install": "Will install into:\n{path}",
        "setup.status.installing": "installing…",
        "setup.status.failed": "Install failed: {error}",
        "setup.installed.tag": "installed",
        "setup.not_installed.tag": "not installed",
        # Blender next steps
        "setup.next_steps.title": "After installing",
        "setup.next_steps.blender.1": "1.  Open Blender",
        "setup.next_steps.blender.2": "2.  Edit → Preferences → Add-ons",
        "setup.next_steps.blender.3": '3.  Search "MCP Server", tick the checkbox',
        "setup.next_steps.blender.4": "4.  3D Viewport → N-Panel → MCP → Start Server",
        "setup.next_steps.blender.5": "5.  The Blender pill should turn green",
        # FreeCAD next steps
        "setup.next_steps.freecad.1": "1.  Open FreeCAD",
        "setup.next_steps.freecad.2": "2.  Macro → Macros → select freecad_mcp_addon",
        "setup.next_steps.freecad.3": "3.  Click Execute",
        "setup.next_steps.freecad.4": "4.  The FreeCAD pill should turn green",
        "setup.next_steps.freecad.note": "Note: the macro must be run each time FreeCAD starts. Installing alone is not enough.",
        # GIMP next steps
        "setup.next_steps.gimp.1": "1.  Restart GIMP",
        "setup.next_steps.gimp.2": "2.  Filters → Python-Fu → MCP Server Start",
        "setup.next_steps.gimp.3": "3.  (GIMP 3.0+: Filters → MCP Server Start)",
        "setup.next_steps.gimp.4": "4.  The GIMP pill should turn green",
        "setup.next_steps.gimp.note": "Note: the server must be started manually each time GIMP starts.",
        # Inkscape info
        "setup.standalone.title": "Standalone servers",
        "setup.standalone.inkscape": (
            "Inkscape  (port 9879)\n"
            "Inkscape doesn't support persistent plugins.  Run the server alongside:\n"
            "   python assets/inkscape_mcp_server.py\n"
            "Requires: pip install lxml"
        ),
        "setup.standalone.photoshop": (
            "Photoshop  (port 9880)\n"
            "Run the server alongside Photoshop:\n"
            "   python assets/photoshop_mcp_server.py\n"
            "Windows: pip install pywin32  |  macOS: no extra deps"
        ),

        # --- models view
        "models.title": "Models",
        "models.subtitle": "Manage local Ollama models. Q4_K_M is the recommended quantization (best quality / size trade-off).",
        "models.installed.title": "Installed",
        "models.installed.empty": "No models installed yet.\nUse the panel on the right to pull one.",
        "models.ollama_offline": "Ollama is offline.\nStart it with `ollama serve`.",
        "models.btn.use": "Use",
        "models.btn.active": "Active",
        "models.pull.title": "Pull a model",
        "models.pull.recommended": "Recommended (defaults to Q4_K_M):",
        "models.pull.placeholder": "e.g. qwen2.5-coder:7b",
        "models.pull.btn": "⬇  Pull model",
        "models.pull.starting": "starting…",
        "models.pull.done": "✓ pulled",
        "models.pull.error": "error: {error}",

        # --- settings view
        "settings.title": "Settings",
        "settings.section.provider": "LLM Provider",
        "settings.section.ollama": "Ollama (local LLM)",
        "settings.section.blender": "Creative App (TCP connection)",
        "settings.section.behaviour": "Behaviour",
        "settings.section.appearance": "Appearance",
        "settings.endpoint": "Endpoint",
        "settings.endpoint.tooltip": "HTTP URL of your Ollama daemon",
        "settings.temperature": "Temperature",
        "settings.temperature.tooltip": "0.0 = deterministic, 0.2 ≈ default, 0.7+ = creative",
        "settings.keepalive": "Keep-alive",
        "settings.keepalive.tooltip": "How long Ollama keeps the model loaded after a request, e.g. 5m, 1h, -1 for forever",
        "settings.host": "Host",
        "settings.host.tooltip": "Usually 127.0.0.1 if the creative app runs on the same machine",
        "settings.port": "Port",
        "settings.port.tooltip": "Default: 9876 (Blender). FreeCAD 9877, GIMP 9878, Inkscape 9879, Photoshop 9880",
        "settings.btn.test_connection": "Test connection",
        "settings.btn.test_connection.tooltip": "Send a ping to the target creative app addon",
        "settings.persist": "Persist conversation history between sessions",
        "settings.persist.tooltip": "Stored at ~/.unification/history.json",
        "settings.route": "Auto-route system prompt (query vs build)",
        "settings.route.tooltip": "Read-only inspections get a shorter prompt; creative builds get the full one",
        "settings.updates": "Check GitHub Releases for updates on startup",
        "settings.updates.tooltip": "Notifies if a newer UNIFICATION release is available",
        "settings.max_history": "Max history tokens",
        "settings.max_history.tooltip": "Older messages are dropped when the conversation exceeds this budget",
        "settings.scene_ctx": "Inject scene context (Blender only)",
        "settings.scene_ctx.tooltip": "Send the list of scene objects to the model before each prompt",
        "settings.max_fix": "Auto-fix attempts",
        "settings.max_fix.tooltip": "Maximum number of automatic correction rounds per turn",
        "settings.num_ctx": "Context window (num_ctx)",
        "settings.num_ctx.tooltip": "Token context size sent to Ollama — increase for large prompts, decrease to save VRAM",
        "settings.theme": "Theme",
        "settings.language": "Language",
        "settings.language.tooltip": "Some labels only refresh after restart",
        "settings.btn.save": "Save settings",
        "settings.provider.api_key": "{provider} API Key",
        "settings.provider.model": "{provider} Model",
        "dialog.export_title": "Export conversation",
        "dialog.attach_title": "Attach an image",

        # --- logs view
        "logs.title": "Logs",
        "logs.empty": "(no events yet)",
        "logs.file": "file: {path}",
        "logs.btn.refresh": "Refresh",
        "logs.btn.clear": "Clear",
        "logs.btn.clear.tooltip": "Wipe in-memory and on-disk log",

        # --- about view
        "about.body": (
            "Vibe codez vos modeles 3D, images et plus encore\n"
            "Blender · FreeCAD · GIMP · Inkscape · Photoshop\n\n"
            "Local-first with Ollama — optionally connect\n"
            "Claude, OpenAI or Gemini via API key.\n\n"
            "Pipeline:  natural-language prompt  →  LLM  →  "
            "Python script  →  TCP MCP addon.\n\n"
            "Recommended local model:  qwen2.5:32b"
        ),
        "about.shortcuts.title": "Keyboard shortcuts",
        "shortcut.send": "Send prompt",
        "shortcut.stop": "Stop streaming",
        "shortcut.clear": "Clear conversation",
        "shortcut.focus": "Focus prompt",
        "shortcut.settings": "Open Settings",
        "shortcut.chat": "Switch to Chat",
        "shortcut.setup": "Switch to Setup",
        "shortcut.models": "Switch to Models",
        "shortcut.logs": "Switch to Logs",

        # --- toasts
        "toast.exported": "Exported",
        "toast.nothing_to_export": "Nothing to export",
        "toast.settings_saved": "Settings saved",
        "toast.invalid_value": "Invalid value: {error}",
        "toast.invalid_port": "Port must be an integer",
        "toast.blender_reachable": "Blender reachable",
        "toast.blender_unreachable": "No response from Blender",
        "toast.model_set": "Model set to {name}",
        "toast.pulled": "Pulled {name}",
        "toast.pull_failed": "Pull failed: {error}",
        "toast.stopped": "Streaming stopped",
        "toast.addon_installed": "Addon installed (v{version})",
        "toast.addon_install_failed": "Install failed: {error}",
        "toast.addon_removed": "Addon removed",
        "toast.addon_remove_failed": "Could not remove the addon file",
        "toast.image_error": "Could not read image: {error}",
        "toast.attach_pick_first": "Type or browse to a folder first",
        "toast.cant_open_explorer": "Could not open file explorer",
        "toast.language_restart": "Language changed — restart the app to apply everywhere",

        # --- dialogs
        "dialog.clear_confirm": "Type OK to clear the conversation:",
        "dialog.clear_title": "Clear conversation?",

        # --- models
        "models.btn.refresh": "Refresh",
        "models.pull.cancelled": "Pull cancelled",
        "models.pull.cancel_tooltip": "Abort model download",

        # --- token budget
        "chat.token_budget.tooltip": "Tokens used / budget — older turns are trimmed automatically",

        # --- empty state suggestion chips — 12 per creative app
        # Blender
        "suggest.blender.1": "Add a metallic donut with colorful sprinkles scattered on top",
        "suggest.blender.2": "Create a low-poly landscape with mountains, pine trees and a lake",
        "suggest.blender.3": "Animate a bouncing rubber ball with squash and stretch over 60 frames",
        "suggest.blender.4": "Set up a 3-point studio lighting rig (key, fill, rim) around the active object",
        "suggest.blender.5": "Create a glass wine bottle with refraction and caustics material",
        "suggest.blender.6": "Add a particle system that emits sparks upward from the selected object",
        "suggest.blender.7": "Build a spiral staircase using an array modifier on a curve path",
        "suggest.blender.8": "Sculpt Suzanne with a Multires modifier (3 subdivisions) ready for the Grab brush",
        "suggest.blender.9": "Create a procedural brick wall using geometry nodes",
        "suggest.blender.10": "Set up a turntable camera that orbits 360° around the origin in 120 frames",
        "suggest.blender.11": "Simulate dominos falling in a chain reaction using rigid body physics",
        "suggest.blender.12": "Create an ocean surface with a foam texture and an HDRI sky background",
        # FreeCAD
        "suggest.freecad.1": "Create a parametric spur gear with 24 teeth, module 2",
        "suggest.freecad.2": "Draw a circular flange with 6 bolt holes evenly spaced",
        "suggest.freecad.3": "Build an L-bracket with 3 mm fillets on all inner edges",
        "suggest.freecad.4": "Model a 90° pipe elbow with inner radius 20 mm and wall thickness 3 mm",
        "suggest.freecad.5": "Design an M10 hex nut (across-flats 17 mm, height 8 mm)",
        "suggest.freecad.6": "Create a phone stand with a 60° back angle and cable slot",
        "suggest.freecad.7": "Build a box with finger joints for 3 mm laser-cut plywood",
        "suggest.freecad.8": "Model a bearing housing with chamfers, fillets and mounting holes",
        "suggest.freecad.9": "Create a helical compression spring (wire Ø 2 mm, 8 coils, OD 20 mm)",
        "suggest.freecad.10": "Design a stepped shaft with three diameters and a keyway slot",
        "suggest.freecad.11": "Boolean-cut a rectangular pocket into the top face of a box",
        "suggest.freecad.12": "Model a T-slot extrusion profile (20×20 mm) for aluminium framing",
        # GIMP
        "suggest.gimp.1": "Create a 1920×1080 gradient background from deep blue to purple",
        "suggest.gimp.2": "Apply a vintage sepia tone effect to the current image",
        "suggest.gimp.3": "Add a drop shadow to the active layer (offset 5 px, blur 10 px)",
        "suggest.gimp.4": "Create a circular vignette: darken the edges of the current photo",
        "suggest.gimp.5": "Sharpen the current image with Unsharp Mask (amount 80, radius 3)",
        "suggest.gimp.6": "Add a text layer with 'UNIFICATION' in white, 72 px, centered",
        "suggest.gimp.7": "Split the image into R, G, B channels as separate grayscale layers",
        "suggest.gimp.8": "Resize the canvas to a 1:1 square and center the existing content",
        "suggest.gimp.9": "Apply a Gaussian blur (radius 12) to everything except the center",
        "suggest.gimp.10": "Draw a 4 px red border around the edges of the image on a new layer",
        "suggest.gimp.11": "Create a duotone effect: map shadows to dark teal, highlights to cream",
        "suggest.gimp.12": "Generate a tileable noise pattern (512×512) for use as a texture",
        # Inkscape
        "suggest.inkscape.1": "Draw a 5-pointed star filled with a gold-to-orange gradient",
        "suggest.inkscape.2": "Create a logo: a circle with the letter 'U' centered inside",
        "suggest.inkscape.3": "Build a colour palette strip — 7 equally-spaced rectangles in rainbow order",
        "suggest.inkscape.4": "Draw a simple flowchart: 3 boxes connected by arrows",
        "suggest.inkscape.5": "Create a sine wave path stretching across the full page width",
        "suggest.inkscape.6": "Design an icon: rounded square with a lightning bolt inside",
        "suggest.inkscape.7": "Draw an 8×8 checkerboard grid of alternating black and white squares",
        "suggest.inkscape.8": "Create a circular badge with the text 'PREMIUM' on a curved path",
        "suggest.inkscape.9": "Build a bar chart with 5 bars of different heights and colours",
        "suggest.inkscape.10": "Draw a fractal tree using recursive branching lines",
        "suggest.inkscape.11": "Create a geometric mandala pattern with 12-fold rotational symmetry",
        "suggest.inkscape.12": "Design a business card layout (85×55 mm) with placeholder text and logo area",
        # Photoshop
        "suggest.photoshop.1": "Create a 4K canvas (3840×2160) with a radial dark-to-midnight gradient",
        "suggest.photoshop.2": "Apply motion blur at 45° angle and 20 px distance to the active layer",
        "suggest.photoshop.3": "Add a Curves adjustment layer to boost midtone contrast",
        "suggest.photoshop.4": "Create a circular layer mask that reveals only the centre of the image",
        "suggest.photoshop.5": "Duplicate the layer, desaturate the copy, set blend mode to Overlay",
        "suggest.photoshop.6": "Add Inner Glow and Bevel & Emboss effects to the active layer",
        "suggest.photoshop.7": "Resize the image to 1920 px wide, keep aspect ratio, sharpen for web",
        "suggest.photoshop.8": "Add a text layer with drop shadow and outer glow effects",
        "suggest.photoshop.9": "Apply a High Pass filter (radius 5) on a duplicate for detail sharpening",
        "suggest.photoshop.10": "Create a 2×2 photo collage grid on a new 4K canvas",
        "suggest.photoshop.11": "Add a Color Lookup adjustment layer for a cinematic orange-teal grade",
        "suggest.photoshop.12": "Create a neon glow text effect with outer glow on a dark background",

        # --- prompt system badges
        "prompt.mode.creator": "creator",
        "prompt.mode.query": "query",
        "prompt.mode.fix": "fix #{n}",
        "cat.materials": "materials",
        "cat.lighting": "lighting",
        "cat.physics": "physics",
        "cat.particles": "particles",
        "cat.sculpting": "sculpting",
        "cat.rendering": "rendering",
        "cat.geometry_nodes": "geo-nodes",
        "cat.modeling": "modeling",
        "cat.animation": "animation",
        "cat.import_export": "import/export",
    },

    "fr": {
        # --- window chrome
        "app.subtitle": "   ·  Vibe codez vos modeles 3D, images et plus encore",
        "header.update.available": "Mise à jour disponible : {version}  ·  voir À propos",
        "header.update.no_network": "",

        # --- sidebar
        "sidebar.chat": "Discussion",
        "sidebar.setup": "Installation",
        "sidebar.models": "Modèles",
        "sidebar.settings": "Paramètres",
        "sidebar.logs": "Journal",
        "sidebar.about": "À propos",
        "sidebar.model_label": "MODÈLE",
        "sidebar.model_tooltip": "Modèle Ollama actif — modifiable à tout moment",

        # --- pills
        "pill.ollama": "Ollama",
        "pill.ollama.offline": "Ollama hors ligne",
        "pill.ollama.tooltip": "Cliquer pour rafraîchir le statut",
        "pill.blender": "Blender",
        "pill.blender.offline": "Blender hors ligne",
        "pill.blender.tooltip": "Cliquer pour pinger l'addon Blender",
        "pill.freecad": "FreeCAD",
        "pill.freecad.offline": "FreeCAD hors ligne",
        "pill.freecad.tooltip": "Cliquer pour pinger l'addon FreeCAD",
        "pill.gimp": "GIMP",
        "pill.gimp.offline": "GIMP hors ligne",
        "pill.gimp.tooltip": "Cliquer pour pinger l'addon GIMP",
        "pill.inkscape": "Inkscape",
        "pill.inkscape.offline": "Inkscape hors ligne",
        "pill.inkscape.tooltip": "Cliquer pour pinger le serveur Inkscape",
        "pill.photoshop": "Photoshop",
        "pill.photoshop.offline": "Photoshop hors ligne",
        "pill.photoshop.tooltip": "Cliquer pour pinger le serveur Photoshop",

        # --- chat / empty state
        "chat.empty.title": "UNIFICATION",
        "chat.empty.subtitle": "Décris ce que tu veux créer.\nOllama génère le code, l'addon l'exécute dans ton appli créative.",
        "chat.placeholder": "Décris une tâche…   (ex. une sphère en verre dans Blender, un cercle rouge dans Inkscape)",
        "chat.hint.send": "Ctrl+Entrée pour envoyer",

        "chat.btn.auto_run": "Auto-exécution",
        "chat.btn.auto_run.tooltip": "Exécute le code généré dès que le streaming est terminé",
        "chat.btn.auto_fix": "Auto-correction",
        "chat.btn.auto_fix.tooltip": "Si Blender renvoie une erreur, demande au modèle de la corriger automatiquement",
        "chat.btn.preview": "Aperçu",
        "chat.btn.preview.tooltip": "Rend un aperçu du viewport après chaque exécution et l'affiche inline",
        "chat.btn.send": "Envoyer  ⏎",
        "chat.btn.send.tooltip": "Envoyer (Ctrl+Entrée)",
        "chat.btn.clear": "Vider",
        "chat.btn.clear.tooltip": "Effacer toute la discussion  (Ctrl+L)",
        "chat.btn.export": "Exporter",
        "chat.btn.export.tooltip": "Sauvegarder toute la conversation au format JSON",
        "chat.btn.attach.tooltip": "Joindre une image (modèles vision uniquement)",
        "chat.attach.remove": "✕  retirer",
        "chat.attach.remove.tooltip": "Retirer cette pièce jointe",

        # --- chat turn
        "turn.assistant": "  Assistant",
        "turn.thinking": "réflexion…",
        "turn.streaming": "génération…",
        "turn.ready": "prêt",
        "turn.stopped": "arrêté",
        "turn.error": "erreur",
        "turn.btn.run": "▶  Exécuter dans Blender",
        "turn.btn.run.prefix": "Exécuter dans",
        "turn.btn.run.tooltip": "Envoyer le code à l'appli créative cible",
        "turn.btn.run.running": "… exécution",
        "turn.btn.regenerate": "↻  Régénérer",
        "turn.btn.regenerate.tooltip": "Redemander au modèle avec le même prompt",
        "turn.btn.save_py": "Sauver .py",
        "turn.btn.save_py.tooltip": "Sauvegarder le script généré dans un fichier .py",
        "code.copy": "Copier",
        "code.copied": "Copié",
        "code.save_title": "Sauvegarder le script Python",
        "code.lines": "{n} lignes",
        "code.line": "{n} ligne",
        "turn.btn.delete": "🗑",
        "turn.btn.delete.tooltip": "Supprimer ce turn de la conversation",
        "turn.btn.stop": "■  Stop",
        "turn.btn.stop.tooltip": "Annuler la génération en cours",
        "turn.result.ok": "✓  Exécuté dans {app}",
        "turn.result.error": "✗  {app} a levé une exception",
        "turn.result.transport_error": "✗  Impossible d'atteindre {app} — l'addon est-il actif ?",
        "turn.result.empty": "(aucune sortie)",
        "turn.attach.caption": "image jointe",
        "turn.preview.caption": "aperçu viewport",
        "turn.fix.attempt": "(tentative auto-correction {n})",

        # --- setup view
        "setup.title": "Installation",
        "setup.intro": (
            "Installe les addons MCP dans tes applis créatives.  "
            "Chaque addon est un petit serveur TCP qui permet à UNIFICATION d'envoyer des scripts."
        ),
        "setup.detected.title": "Installations détectées",
        "setup.bundled_version": "Addon embarqué : v{version}",
        "setup.btn.refresh": "Rafraîchir",
        "setup.no_install": (
            "Aucune installation détectée automatiquement.\n"
            "Ajoute un chemin manuellement ci-dessous."
        ),
        "setup.no_install.blender": (
            "Aucune installation Blender détectée.\n"
            "Ajoute un chemin manuellement — typiquement :\n"
            "   %APPDATA%\\Blender Foundation\\Blender\\<X.Y>\\scripts\\addons"
        ),
        "setup.no_install.freecad": (
            "Aucune installation FreeCAD détectée.\n"
            "Ajoute un chemin manuellement — typiquement :\n"
            "   %APPDATA%\\FreeCAD\\Macro\\"
        ),
        "setup.no_install.gimp": (
            "Aucune installation GIMP détectée.\n"
            "Ajoute un chemin manuellement — typiquement :\n"
            "   %APPDATA%\\GIMP\\2.10\\plug-ins\\"
        ),
        "setup.custom_path": "Chemin personnalisé",
        "setup.btn.browse": "Parcourir",
        "setup.btn.browse.tooltip": "Choisir un dossier d'addons",
        "setup.btn.use": "Ajouter",
        "setup.btn.use.tooltip": "Ajouter ce dossier à la liste",
        "setup.source.title": "Source d'installation",
        "setup.source.remote": "Dernière version GitHub",
        "setup.source.bundled": "Embarqué (hors ligne)",
        "setup.source.bundled.tooltip": "Utiliser le .py livré avec l'app",
        "setup.btn.install": "⬇  Installer / Mettre à jour",
        "setup.btn.reinstall": "⟳  Réinstaller / mettre à jour",
        "setup.btn.install_only": "⬇  Installer l'addon",
        "setup.btn.open_folder": "📂  Ouvrir le dossier",
        "setup.btn.open_folder.tooltip": "Révéler le dossier d'addons dans l'explorateur",
        "setup.btn.uninstall": "🗑  Désinstaller",
        "setup.btn.uninstall.tooltip": "Retirer l'addon du dossier sélectionné",
        "setup.status.select": "Sélectionne un dossier ci-dessus.",
        "setup.status.installed": "v{version} installé dans :\n{path}",
        "setup.status.will_install": "Sera installé dans :\n{path}",
        "setup.status.installing": "installation…",
        "setup.status.failed": "Échec de l'installation : {error}",
        "setup.installed.tag": "installé",
        "setup.not_installed.tag": "non installé",
        # Blender
        "setup.next_steps.title": "Après l'installation",
        "setup.next_steps.blender.1": "1.  Ouvre Blender",
        "setup.next_steps.blender.2": "2.  Édition → Préférences → Add-ons",
        "setup.next_steps.blender.3": "3.  Cherche « MCP Server », coche la case",
        "setup.next_steps.blender.4": "4.  Viewport 3D → N-Panel → MCP → Start Server",
        "setup.next_steps.blender.5": "5.  La pastille Blender doit passer au vert",
        # FreeCAD
        "setup.next_steps.freecad.1": "1.  Ouvre FreeCAD",
        "setup.next_steps.freecad.2": "2.  Macro → Macros → sélectionne freecad_mcp_addon",
        "setup.next_steps.freecad.3": "3.  Clique Exécuter",
        "setup.next_steps.freecad.4": "4.  La pastille FreeCAD doit passer au vert",
        "setup.next_steps.freecad.note": "Note : la macro doit être lancée à chaque démarrage de FreeCAD. L'installation seule ne suffit pas.",
        # GIMP
        "setup.next_steps.gimp.1": "1.  Redémarre GIMP",
        "setup.next_steps.gimp.2": "2.  Filtres → Python-Fu → MCP Server Start",
        "setup.next_steps.gimp.3": "3.  (GIMP 3.0+ : Filtres → MCP Server Start)",
        "setup.next_steps.gimp.4": "4.  La pastille GIMP doit passer au vert",
        "setup.next_steps.gimp.note": "Note : le serveur doit être démarré manuellement à chaque lancement de GIMP.",
        # Standalone
        "setup.standalone.title": "Serveurs standalone",
        "setup.standalone.inkscape": (
            "Inkscape  (port 9879)\n"
            "Inkscape ne supporte pas les plugins persistants.  Lance le serveur à côté :\n"
            "   python assets/inkscape_mcp_server.py\n"
            "Requis : pip install lxml"
        ),
        "setup.standalone.photoshop": (
            "Photoshop  (port 9880)\n"
            "Lance le serveur à côté de Photoshop :\n"
            "   python assets/photoshop_mcp_server.py\n"
            "Windows : pip install pywin32  |  macOS : aucune dépendance"
        ),

        # --- models view
        "models.title": "Modèles",
        "models.subtitle": "Gère tes modèles Ollama locaux. Q4_K_M est la quantization recommandée (meilleur compromis qualité / taille).",
        "models.installed.title": "Installés",
        "models.installed.empty": "Aucun modèle installé pour l'instant.\nUtilise le panneau de droite pour en télécharger un.",
        "models.ollama_offline": "Ollama est hors ligne.\nDémarre-le avec `ollama serve`.",
        "models.btn.use": "Utiliser",
        "models.btn.active": "Actif",
        "models.pull.title": "Télécharger un modèle",
        "models.pull.recommended": "Recommandés (Q4_K_M par défaut) :",
        "models.pull.placeholder": "ex. qwen2.5-coder:7b",
        "models.pull.btn": "⬇  Télécharger",
        "models.pull.starting": "démarrage…",
        "models.pull.done": "✓ téléchargé",
        "models.pull.error": "erreur : {error}",

        # --- settings view
        "settings.title": "Paramètres",
        "settings.section.provider": "Fournisseur LLM",
        "settings.section.ollama": "Ollama (LLM local)",
        "settings.section.blender": "Appli creative (connexion TCP)",
        "settings.section.behaviour": "Comportement",
        "settings.section.appearance": "Apparence",
        "settings.endpoint": "Endpoint",
        "settings.endpoint.tooltip": "URL HTTP du démon Ollama",
        "settings.temperature": "Température",
        "settings.temperature.tooltip": "0.0 = déterministe, 0.2 ≈ défaut, 0.7+ = créatif",
        "settings.keepalive": "Keep-alive",
        "settings.keepalive.tooltip": "Durée pendant laquelle Ollama garde le modèle chargé après une requête (ex. 5m, 1h, -1 pour toujours)",
        "settings.host": "Hôte",
        "settings.host.tooltip": "Généralement 127.0.0.1 si l'appli créative tourne sur la même machine",
        "settings.port": "Port",
        "settings.port.tooltip": "Défaut : 9876 (Blender). FreeCAD 9877, GIMP 9878, Inkscape 9879, Photoshop 9880",
        "settings.btn.test_connection": "Tester la connexion",
        "settings.btn.test_connection.tooltip": "Envoie un ping à l'addon de l'appli cible",
        "settings.persist": "Conserver l'historique entre les sessions",
        "settings.persist.tooltip": "Stocké dans ~/.unification/history.json",
        "settings.route": "Routage automatique du system prompt (lecture / création)",
        "settings.route.tooltip": "Les inspections lecture seule reçoivent un prompt court ; les créations le prompt complet",
        "settings.updates": "Vérifier les mises à jour GitHub au démarrage",
        "settings.updates.tooltip": "Notifie si une nouvelle version d'UNIFICATION est disponible",
        "settings.max_history": "Tokens d'historique max",
        "settings.max_history.tooltip": "Les anciens messages sont droppés au-delà de ce budget",
        "settings.scene_ctx": "Injecter le contexte de la scène (Blender uniquement)",
        "settings.scene_ctx.tooltip": "Envoyer la liste des objets de la scène au modèle avant chaque prompt",
        "settings.max_fix": "Tentatives auto-correction",
        "settings.max_fix.tooltip": "Nombre maximal de cycles automatiques de correction par turn",
        "settings.num_ctx": "Fenêtre de contexte (num_ctx)",
        "settings.num_ctx.tooltip": "Taille du contexte envoyé à Ollama — augmenter pour les gros prompts, réduire pour économiser la VRAM",
        "settings.theme": "Thème",
        "settings.language": "Langue",
        "settings.language.tooltip": "Certains libellés ne se rafraîchissent qu'au redémarrage",
        "settings.btn.save": "Enregistrer",
        "settings.provider.api_key": "Clé API {provider}",
        "settings.provider.model": "Modèle {provider}",
        "dialog.export_title": "Exporter la conversation",
        "dialog.attach_title": "Joindre une image",

        # --- logs view
        "logs.title": "Journal",
        "logs.empty": "(aucun événement pour l'instant)",
        "logs.file": "fichier : {path}",
        "logs.btn.refresh": "Rafraîchir",
        "logs.btn.clear": "Vider",
        "logs.btn.clear.tooltip": "Effacer le journal en mémoire et sur disque",

        # --- about view
        "about.body": (
            "Vibe codez vos modeles 3D, images et plus encore\n"
            "Blender · FreeCAD · GIMP · Inkscape · Photoshop\n\n"
            "Local d'abord avec Ollama — connecte\n"
            "Claude, OpenAI ou Gemini via clé d'API.\n\n"
            "Pipeline :  prompt en langage naturel  →  LLM  →  "
            "script Python  →  addon TCP MCP.\n\n"
            "Modèle local recommandé :  qwen2.5:32b"
        ),
        "about.shortcuts.title": "Raccourcis clavier",
        "shortcut.send": "Envoyer le prompt",
        "shortcut.stop": "Arrêter le streaming",
        "shortcut.clear": "Vider la discussion",
        "shortcut.focus": "Focus sur le prompt",
        "shortcut.settings": "Ouvrir les paramètres",
        "shortcut.chat": "Aller dans Discussion",
        "shortcut.setup": "Aller dans Installation",
        "shortcut.models": "Aller dans Modèles",
        "shortcut.logs": "Aller dans Journal",

        # --- toasts
        "toast.exported": "Exporté",
        "toast.nothing_to_export": "Rien à exporter",
        "toast.settings_saved": "Paramètres enregistrés",
        "toast.invalid_value": "Valeur invalide : {error}",
        "toast.invalid_port": "Le port doit être un entier",
        "toast.blender_reachable": "Blender accessible",
        "toast.blender_unreachable": "Blender ne répond pas",
        "toast.model_set": "Modèle défini sur {name}",
        "toast.pulled": "{name} téléchargé",
        "toast.pull_failed": "Échec du téléchargement : {error}",
        "toast.stopped": "Streaming arrêté",
        "toast.addon_installed": "Addon installé (v{version})",
        "toast.addon_install_failed": "Échec de l'installation : {error}",
        "toast.addon_removed": "Addon retiré",
        "toast.addon_remove_failed": "Impossible de supprimer le fichier addon",
        "toast.image_error": "Impossible de lire l'image : {error}",
        "toast.attach_pick_first": "Saisis ou parcours un dossier d'abord",
        "toast.cant_open_explorer": "Impossible d'ouvrir l'explorateur",
        "toast.language_restart": "Langue modifiée — redémarre l'app pour appliquer partout",

        # --- dialogs
        "dialog.clear_confirm": "Tape OK pour vider la conversation :",
        "dialog.clear_title": "Vider la conversation ?",

        # --- models
        "models.btn.refresh": "Rafraîchir",
        "models.pull.cancelled": "Téléchargement annulé",
        "models.pull.cancel_tooltip": "Annuler le téléchargement",

        # --- token budget
        "chat.token_budget.tooltip": "Tokens utilisés / budget — les anciens turns sont coupés automatiquement",

        # --- empty state suggestion chips — 12 par appli créative
        # Blender
        "suggest.blender.1": "Ajoute un donut métallique avec des vermicelles colorés par-dessus",
        "suggest.blender.2": "Crée un paysage low-poly avec des montagnes, des sapins et un lac",
        "suggest.blender.3": "Anime une balle en caoutchouc qui rebondit avec squash & stretch sur 60 frames",
        "suggest.blender.4": "Installe un éclairage studio 3 points (key, fill, rim) autour de l'objet actif",
        "suggest.blender.5": "Crée une bouteille en verre avec un matériau réfractif et caustiques",
        "suggest.blender.6": "Ajoute un système de particules qui émet des étincelles vers le haut depuis l'objet sélectionné",
        "suggest.blender.7": "Construis un escalier en colimaçon avec un Array modifier sur une courbe",
        "suggest.blender.8": "Sculpte Suzanne avec un modificateur Multires (3 subdivisions) prêt pour le brush Grab",
        "suggest.blender.9": "Crée un mur de briques procédural avec les geometry nodes",
        "suggest.blender.10": "Mets en place une caméra turntable qui orbite 360° autour de l'origine en 120 frames",
        "suggest.blender.11": "Simule des dominos qui tombent en chaîne avec la physique rigid body",
        "suggest.blender.12": "Crée une surface d'océan avec texture d'écume et un ciel HDRI en fond",
        # FreeCAD
        "suggest.freecad.1": "Crée un engrenage droit paramétrique à 24 dents, module 2",
        "suggest.freecad.2": "Dessine une bride circulaire avec 6 trous de boulons répartis uniformément",
        "suggest.freecad.3": "Construis une équerre en L avec des congés de 3 mm sur les arêtes intérieures",
        "suggest.freecad.4": "Modélise un coude de tuyau à 90° avec un rayon intérieur de 20 mm et une épaisseur de 3 mm",
        "suggest.freecad.5": "Conçois un écrou hexagonal M10 (surplats 17 mm, hauteur 8 mm)",
        "suggest.freecad.6": "Crée un support de téléphone avec un angle de dossier à 60° et une fente pour le câble",
        "suggest.freecad.7": "Construis une boîte à joints en doigt pour du contreplaqué 3 mm découpé au laser",
        "suggest.freecad.8": "Modélise un palier avec chanfreins, congés et trous de fixation",
        "suggest.freecad.9": "Crée un ressort de compression hélicoïdal (fil Ø 2 mm, 8 spires, ØE 20 mm)",
        "suggest.freecad.10": "Conçois un arbre étagé à trois diamètres avec une rainure de clavette",
        "suggest.freecad.11": "Fais une coupe booléenne d'une poche rectangulaire dans la face supérieure d'un bloc",
        "suggest.freecad.12": "Modélise un profilé à rainure en T (20×20 mm) pour cadre aluminium",
        # GIMP
        "suggest.gimp.1": "Crée un fond dégradé 1920×1080 du bleu profond au violet",
        "suggest.gimp.2": "Applique un effet sépia vintage à l'image actuelle",
        "suggest.gimp.3": "Ajoute une ombre portée au calque actif (décalage 5 px, flou 10 px)",
        "suggest.gimp.4": "Crée un vignettage circulaire : assombris les bords de la photo",
        "suggest.gimp.5": "Accentue la netteté avec un masque flou (quantité 80, rayon 3)",
        "suggest.gimp.6": "Ajoute un calque texte avec 'UNIFICATION' en blanc, 72 px, centré",
        "suggest.gimp.7": "Sépare l'image en canaux R, V, B comme calques distincts en niveaux de gris",
        "suggest.gimp.8": "Redimensionne le canevas en carré 1:1 et centre le contenu existant",
        "suggest.gimp.9": "Applique un flou gaussien (rayon 12) partout sauf au centre de l'image",
        "suggest.gimp.10": "Dessine un cadre rouge de 4 px autour de l'image sur un nouveau calque",
        "suggest.gimp.11": "Crée un effet bichromie : ombres en bleu sarcelle foncé, hautes lumières en crème",
        "suggest.gimp.12": "Génère un motif de bruit tileable (512×512) utilisable comme texture",
        # Inkscape
        "suggest.inkscape.1": "Dessine une étoile à 5 branches remplie d'un dégradé or à orange",
        "suggest.inkscape.2": "Crée un logo : un cercle avec la lettre « U » centrée à l'intérieur",
        "suggest.inkscape.3": "Construis une bande de palette — 7 rectangles aux couleurs de l'arc-en-ciel",
        "suggest.inkscape.4": "Dessine un organigramme simple : 3 boîtes reliées par des flèches",
        "suggest.inkscape.5": "Crée un chemin sinusoïdal traversant toute la largeur de la page",
        "suggest.inkscape.6": "Conçois une icône : carré arrondi avec un éclair à l'intérieur",
        "suggest.inkscape.7": "Dessine un damier 8×8 de cases alternées noir et blanc",
        "suggest.inkscape.8": "Crée un badge circulaire avec le texte « PREMIUM » sur un chemin courbe",
        "suggest.inkscape.9": "Construis un diagramme à barres avec 5 barres de hauteurs et couleurs différentes",
        "suggest.inkscape.10": "Dessine un arbre fractal avec des branches récursives",
        "suggest.inkscape.11": "Crée un mandala géométrique avec une symétrie rotationnelle d'ordre 12",
        "suggest.inkscape.12": "Conçois une carte de visite (85×55 mm) avec texte et zone logo",
        # Photoshop
        "suggest.photoshop.1": "Crée un canevas 4K (3840×2160) avec un dégradé radial sombre vers bleu nuit",
        "suggest.photoshop.2": "Applique un flou de mouvement à 45° et 20 px sur le calque actif",
        "suggest.photoshop.3": "Ajoute un calque de réglage Courbes pour renforcer le contraste des tons moyens",
        "suggest.photoshop.4": "Crée un masque de calque circulaire qui ne révèle que le centre de l'image",
        "suggest.photoshop.5": "Duplique le calque, désature la copie, et passe le mode de fusion en Incrustation",
        "suggest.photoshop.6": "Ajoute des effets Lueur interne et Biseautage/Estampage au calque actif",
        "suggest.photoshop.7": "Redimensionne l'image à 1920 px de large en conservant les proportions et accentue pour le web",
        "suggest.photoshop.8": "Ajoute un calque texte avec ombre portée et lueur externe",
        "suggest.photoshop.9": "Applique un filtre Passe-haut (rayon 5) sur un duplicata pour l'accentuation des détails",
        "suggest.photoshop.10": "Crée un collage photo 2×2 sur un nouveau canevas 4K",
        "suggest.photoshop.11": "Ajoute un calque de réglage Correspondance de couleur pour un rendu cinéma orange-sarcelle",
        "suggest.photoshop.12": "Crée un effet texte néon lumineux avec lueur externe sur fond noir",

        # --- prompt system badges
        "prompt.mode.creator": "créateur",
        "prompt.mode.query": "requête",
        "prompt.mode.fix": "fix #{n}",
        "cat.materials": "matériaux",
        "cat.lighting": "éclairage",
        "cat.physics": "physique",
        "cat.particles": "particules",
        "cat.sculpting": "sculpture",
        "cat.rendering": "rendu",
        "cat.geometry_nodes": "géo-nodes",
        "cat.modeling": "modélisation",
        "cat.animation": "animation",
        "cat.import_export": "import/export",
    },
}


# Display name shown in the language selector
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "fr": "Français",
}


def available_languages() -> Iterable[str]:
    """Stable order: English first, then alphabetical."""
    return ["en"] + sorted(k for k in TRANSLATIONS if k != "en")


def detect_locale() -> str:
    """Return 'fr' or 'en' based on the OS locale, defaulting to 'en'."""
    try:
        sys_lang, _ = locale.getlocale() or ("", "")
        if sys_lang and sys_lang.lower().startswith(("fr", "french")):
            return "fr"
    except Exception:
        pass
    return "en"


# ---------------------------------------------------------------- runtime


class _Translator:
    def __init__(self) -> None:
        self.lang: str = "en"

    def set(self, lang: str) -> str:
        """Resolves 'auto' against the OS locale, normalises unknown codes to 'en'.

        Returns the resolved code (useful for display).
        """
        if lang == "auto" or not lang:
            lang = detect_locale()
        self.lang = lang if lang in TRANSLATIONS else "en"
        return self.lang

    def get(self, key: str, **kwargs) -> str:
        text = (
            TRANSLATIONS.get(self.lang, {}).get(key)
            or TRANSLATIONS["en"].get(key)
            or key
        )
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text


_translator = _Translator()


def set_language(lang: str) -> str:
    return _translator.set(lang)


def get_language() -> str:
    return _translator.lang


def t(key: str, **kwargs) -> str:
    return _translator.get(key, **kwargs)
