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
        "turn.btn.run.tooltip": "Send the (possibly edited) code to the Blender addon",
        "turn.btn.run.running": "… running",
        "turn.btn.regenerate": "↻  Regenerate",
        "turn.btn.regenerate.tooltip": "Re-ask the model with the same prompt",
        "turn.btn.save_py": "Save .py",
        "turn.btn.save_py.tooltip": "Save the generated script to a .py file",
        "turn.btn.delete": "🗑",
        "turn.btn.delete.tooltip": "Remove this turn from the conversation",
        "turn.btn.stop": "■  Stop",
        "turn.btn.stop.tooltip": "Cancel the streaming response",
        "turn.result.ok": "✓  Executed in Blender",
        "turn.result.error": "✗  Blender raised an exception",
        "turn.result.transport_error": "✗  Cannot reach Blender — is the addon running?",
        "turn.result.empty": "(no output)",
        "turn.attach.caption": "attached image",
        "turn.preview.caption": "viewport preview",
        "turn.fix.attempt": "(auto-fix attempt {n})",

        # --- setup view
        "setup.title": "Setup",
        "setup.intro": (
            "UNIFICATION talks to creative apps through MCP addons "
            "(tiny TCP servers on ports 9876-9880).  For Blender, install the addon once, "
            "then enable it from Edit → Preferences → Add-ons."
        ),
        "setup.detected.title": "Detected Blender installs",
        "setup.bundled_version": "Bundled addon: v{version}",
        "setup.btn.refresh": "Refresh",
        "setup.no_install": (
            "No Blender install detected automatically.\n"
            "Add a path manually below — typically:\n"
            "   %APPDATA%\\Blender Foundation\\Blender\\<X.Y>\\scripts\\addons"
        ),
        "setup.custom_path": "Custom path",
        "setup.btn.browse": "Browse",
        "setup.btn.browse.tooltip": "Pick a Blender addons directory",
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
        "setup.next_steps.title": "After installing",
        "setup.next_steps.1": "1.  Open Blender",
        "setup.next_steps.2": "2.  Edit → Preferences → Add-ons",
        "setup.next_steps.3": "3.  Search “MCP Server”, tick the checkbox",
        "setup.next_steps.4": "4.  3D Viewport → N-Panel → MCP",
        "setup.next_steps.5": "5.  Come back to Chat — both pills should be green",

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
        "settings.section.ollama": "Ollama (local LLM)",
        "settings.section.blender": "Blender (TCP addon)",
        "settings.section.behaviour": "Behaviour",
        "settings.section.appearance": "Appearance",
        "settings.endpoint": "Endpoint",
        "settings.endpoint.tooltip": "HTTP URL of your Ollama daemon",
        "settings.temperature": "Temperature",
        "settings.temperature.tooltip": "0.0 = deterministic, 0.2 ≈ default, 0.7+ = creative",
        "settings.keepalive": "Keep-alive",
        "settings.keepalive.tooltip": "How long Ollama keeps the model loaded after a request, e.g. 5m, 1h, -1 for forever",
        "settings.host": "Host",
        "settings.host.tooltip": "Usually 127.0.0.1 if Blender runs on the same machine",
        "settings.port": "Port",
        "settings.port.tooltip": "The addon defaults to 9876",
        "settings.btn.test_connection": "Test connection",
        "settings.btn.test_connection.tooltip": "Send a ping to the Blender addon",
        "settings.persist": "Persist conversation history between sessions",
        "settings.persist.tooltip": "Stored at ~/.unification/history.json",
        "settings.route": "Auto-route system prompt (query vs build)",
        "settings.route.tooltip": "Read-only inspections get a shorter prompt; creative builds get the full one",
        "settings.updates": "Check GitHub Releases for updates on startup",
        "settings.updates.tooltip": "Notifies if a newer UNIFICATION release is available",
        "settings.max_history": "Max history tokens",
        "settings.max_history.tooltip": "Older messages are dropped when the conversation exceeds this budget",
        "settings.max_fix": "Auto-fix attempts",
        "settings.max_fix.tooltip": "Maximum number of automatic correction rounds per turn",
        "settings.theme": "Theme",
        "settings.language": "Language",
        "settings.language.tooltip": "Some labels only refresh after restart",
        "settings.btn.save": "Save settings",

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
            "100 % local — no Anthropic, no OpenAI, no API key.\n\n"
            "Pipeline:  natural-language prompt  →  Ollama  →  "
            "Python script  →  TCP MCP addon.\n\n"
            "Recommended model:  qwen2.5:32b"
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

        # --- empty state suggestion chips (sculpting-focused)
        "suggest.sculpt_suzanne": "Add Suzanne, give it a Multires modifier (3 subdivisions), then switch to Sculpt mode ready for the Grab brush",
        "suggest.sculpt_dyntopo": "Spawn an icosphere, enable Dyntopo (detail 2.0) and enter Sculpt mode",
        "suggest.sculpt_voxel_remesh": "Voxel-remesh the active mesh at 0.05, then enter Sculpt mode for further detailing",
        "suggest.sculpt_mirror_multires": "Add a Mirror modifier (X axis) and a Multires modifier (level 4) to the active mesh for symmetric sculpting",
        "suggest.sculpt_shape_keys": "Create three shape keys on the active mesh — smile, frown, surprise — leaving each value at 0 for now",
        "suggest.sculpt_decimate": "Decimate the active sculpt to 25 % polycount and apply it, ready for retopology baking",
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
        "turn.btn.run.tooltip": "Envoyer le code (éventuellement édité) à l'addon Blender",
        "turn.btn.run.running": "… exécution",
        "turn.btn.regenerate": "↻  Régénérer",
        "turn.btn.regenerate.tooltip": "Redemander au modèle avec le même prompt",
        "turn.btn.save_py": "Sauver .py",
        "turn.btn.save_py.tooltip": "Sauvegarder le script généré dans un fichier .py",
        "turn.btn.delete": "🗑",
        "turn.btn.delete.tooltip": "Supprimer ce turn de la conversation",
        "turn.btn.stop": "■  Stop",
        "turn.btn.stop.tooltip": "Annuler la génération en cours",
        "turn.result.ok": "✓  Exécuté dans Blender",
        "turn.result.error": "✗  Blender a levé une exception",
        "turn.result.transport_error": "✗  Impossible d'atteindre Blender — l'addon est-il actif ?",
        "turn.result.empty": "(aucune sortie)",
        "turn.attach.caption": "image jointe",
        "turn.preview.caption": "aperçu viewport",
        "turn.fix.attempt": "(tentative auto-correction {n})",

        # --- setup view
        "setup.title": "Installation",
        "setup.intro": (
            "UNIFICATION communique avec les applis créatives via des addons MCP "
            "(petits serveurs TCP sur les ports 9876-9880).  Pour Blender, installe l'addon une fois, "
            "puis active-le depuis Édition → Préférences → Add-ons."
        ),
        "setup.detected.title": "Installations Blender détectées",
        "setup.bundled_version": "Addon embarqué : v{version}",
        "setup.btn.refresh": "Rafraîchir",
        "setup.no_install": (
            "Aucune installation Blender détectée automatiquement.\n"
            "Ajoute un chemin manuellement ci-dessous — typiquement :\n"
            "   %APPDATA%\\Blender Foundation\\Blender\\<X.Y>\\scripts\\addons"
        ),
        "setup.custom_path": "Chemin personnalisé",
        "setup.btn.browse": "Parcourir",
        "setup.btn.browse.tooltip": "Choisir un dossier d'addons Blender",
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
        "setup.next_steps.title": "Après l'installation",
        "setup.next_steps.1": "1.  Ouvre Blender",
        "setup.next_steps.2": "2.  Édition → Préférences → Add-ons",
        "setup.next_steps.3": "3.  Cherche « MCP Server », coche la case",
        "setup.next_steps.4": "4.  Viewport 3D → N-Panel → MCP",
        "setup.next_steps.5": "5.  Reviens dans Discussion — les deux pastilles doivent passer au vert",

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
        "settings.section.ollama": "Ollama (LLM local)",
        "settings.section.blender": "Blender (addon TCP)",
        "settings.section.behaviour": "Comportement",
        "settings.section.appearance": "Apparence",
        "settings.endpoint": "Endpoint",
        "settings.endpoint.tooltip": "URL HTTP du démon Ollama",
        "settings.temperature": "Température",
        "settings.temperature.tooltip": "0.0 = déterministe, 0.2 ≈ défaut, 0.7+ = créatif",
        "settings.keepalive": "Keep-alive",
        "settings.keepalive.tooltip": "Durée pendant laquelle Ollama garde le modèle chargé après une requête (ex. 5m, 1h, -1 pour toujours)",
        "settings.host": "Hôte",
        "settings.host.tooltip": "Généralement 127.0.0.1 si Blender tourne sur la même machine",
        "settings.port": "Port",
        "settings.port.tooltip": "L'addon utilise 9876 par défaut",
        "settings.btn.test_connection": "Tester la connexion",
        "settings.btn.test_connection.tooltip": "Envoie un ping à l'addon Blender",
        "settings.persist": "Conserver l'historique entre les sessions",
        "settings.persist.tooltip": "Stocké dans ~/.unification/history.json",
        "settings.route": "Routage automatique du system prompt (lecture / création)",
        "settings.route.tooltip": "Les inspections lecture seule reçoivent un prompt court ; les créations le prompt complet",
        "settings.updates": "Vérifier les mises à jour GitHub au démarrage",
        "settings.updates.tooltip": "Notifie si une nouvelle version d'UNIFICATION est disponible",
        "settings.max_history": "Tokens d'historique max",
        "settings.max_history.tooltip": "Les anciens messages sont droppés au-delà de ce budget",
        "settings.max_fix": "Tentatives auto-correction",
        "settings.max_fix.tooltip": "Nombre maximal de cycles automatiques de correction par turn",
        "settings.theme": "Thème",
        "settings.language": "Langue",
        "settings.language.tooltip": "Certains libellés ne se rafraîchissent qu'au redémarrage",
        "settings.btn.save": "Enregistrer",

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
            "100 % local — sans Anthropic, sans OpenAI, sans clé d'API.\n\n"
            "Pipeline :  prompt en langage naturel  →  Ollama  →  "
            "script Python  →  addon TCP MCP.\n\n"
            "Modèle recommandé :  qwen2.5:32b"
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

        # --- empty state suggestion chips (sculpting-focused, in French)
        "suggest.sculpt_suzanne": "Ajoute Suzanne, applique un modificateur Multires (3 subdivisions), puis bascule en mode Sculpt prêt pour le brush Grab",
        "suggest.sculpt_dyntopo": "Crée une icosphère, active Dyntopo (détail 2,0) et entre en mode Sculpt",
        "suggest.sculpt_voxel_remesh": "Voxel-remesh l'objet actif à 0,05, puis entre en mode Sculpt pour le détaillage",
        "suggest.sculpt_mirror_multires": "Ajoute un modificateur Mirror (axe X) et un Multires (niveau 4) à l'objet actif pour un sculpting symétrique",
        "suggest.sculpt_shape_keys": "Crée trois shape keys sur l'objet actif — smile, frown, surprise — toutes à la valeur 0 pour l'instant",
        "suggest.sculpt_decimate": "Décime le sculpt actif à 25 % de polygones et applique, prêt pour le baking de retopologie",
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
