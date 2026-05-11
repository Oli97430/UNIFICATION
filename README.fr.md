<h1 align="center">UNIFICATION</h1>

<p align="center">
  <img src="assets/logo.png" alt="Logo UNIFICATION" width="140" />
</p>

<p align="center">
  <b>Vibe codez vos modeles 3D, images et plus encore</b><br/>
  Blender · FreeCAD · GIMP · Inkscape · Photoshop — 100&nbsp;% local, sans cle d'API, sans cloud.<br/>
  Prompt en langage naturel → Ollama → script Python → addon TCP MCP.
</p>

<p align="center">
  <a href="https://github.com/Oli97430/UNIFICATION/releases/latest">
    <img src="https://img.shields.io/github/v/release/Oli97430/UNIFICATION?display_name=tag&color=ff7a29" alt="Derniere version"/>
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/blender-4.0%2B-orange" alt="Blender 4.0+"/>
  <img src="https://img.shields.io/badge/FreeCAD-0.20%2B-009900" alt="FreeCAD 0.20+"/>
  <img src="https://img.shields.io/badge/GIMP-2.10%20%7C%203.x-9B8E00" alt="GIMP 2.10 | 3.x"/>
  <img src="https://img.shields.io/badge/Inkscape-1.x-333333" alt="Inkscape 1.x"/>
  <img src="https://img.shields.io/badge/Photoshop-CC-31A8FF" alt="Photoshop CC"/>
  <img src="https://img.shields.io/badge/licence-GPL--3.0-green" alt="GPL-3.0"/>
</p>

<p align="center">
  🇬🇧 <a href="README.md">English version</a>
</p>

---

## Sommaire

- [Ce que ca fait](#ce-que-ca-fait)
- [Fonctionnalites](#fonctionnalites)
- [Demarrage rapide](#demarrage-rapide)
- [Configuration des applis creatives](#configuration-des-applis-creatives)
- [Serveur MCP pour Claude Desktop / Cursor](#serveur-mcp-pour-claude-desktop--cursor)
- [Modeles recommandes](#modeles-recommandes)
- [Architecture](#architecture)
- [Protocole TCP](#protocole-tcp)
- [Raccourcis clavier](#raccourcis-clavier)
- [Reglages](#reglages)
- [Fichiers utilisateur](#fichiers-utilisateur)
- [Troubleshooting](#troubleshooting)
- [Build & release](#build--release)
- [Licence](#licence)

---

## Ce que ca fait

UNIFICATION est un client desktop moderne (construit avec `customtkinter`) qui fait le pont entre un LLM **local** Ollama et **cinq applications creatives** :

| Appli | Port | Type d'addon | Ce que tu peux faire |
|---|---|---|---|
| **Blender** | 9876 | Addon integre (N-Panel) | Modeliser, animer, rendre, sculpter, shader — API `bpy` complete |
| **FreeCAD** | 9877 | Plugin Macro | CAO parametrique, scripts Part/Draft/Sketch |
| **GIMP** | 9878 | Plugin Python-Fu | Retouche d'image, filtres, traitement par lots |
| **Inkscape** | 9879 | Serveur standalone | Manipulation SVG via lxml/inkex + CLI Inkscape |
| **Photoshop** | 9880 | Serveur standalone | Automatisation COM (Win) / AppleScript (macOS) + ExtendScript |

Tu decris ce que tu veux en langage naturel ; l'app demande a Ollama d'ecrire le script Python, puis l'execute dans ton appli creative via un socket TCP — **sans qu'un seul octet quitte ta machine**.

| | |
|---|---|
| **Zero cloud** | Chaque token reste local. Aucun quota, aucune facturation, aucune fuite de donnees. |
| **Installation addon en un clic** | L'app detecte toutes les installations Blender presentes sur ton systeme et copie l'addon a la bonne place. |
| **Auto-fix sur erreur** | Quand Blender leve une exception, la traceback est renvoyee au modele pour une auto-correction silencieuse. |
| **Durci pour Blender 4.x** | System prompt renforce + sanitizer AST avec **7 regles de reecriture** qui corrigent les appels API casses avant qu'ils n'atteignent Blender. |
| **Support vision** | Attache une image de reference quand tu utilises un modele vision (`qwen2.5-vl`, `llava`, …). |
| **Multilingue** | Interface complete EN / FR — detectee automatiquement depuis la locale de l'OS. |
| **Serveur MCP** | Serveur unifie stdio JSON-RPC 2.0 pour Claude Desktop / Cursor — controle les 5 applis depuis un seul endpoint. |

---

## Fonctionnalites

### Setup & onboarding
- **Installateur d'addon Blender integre** — detecte automatiquement les dossiers Blender sur Windows, macOS, Linux (y compris Snap et Flatpak). Telecharge la derniere version depuis GitHub ; utilise le bundle hors-ligne en fallback.
- **Gestionnaire de modeles** — liste, change et `ollama pull` avec barre de progression et bouton d'annulation, directement depuis l'app.
- **Pastilles de statut live** pour Ollama + les 5 applis creatives (cliquables pour forcer un rafraichissement). Pings TCP en parallele — tout est verifie simultanement.
- **Verification de mise a jour silencieuse** au demarrage — notification toast si une version plus recente existe sur GitHub.

### Chat & generation de code
- **Streaming token par token** avec bouton Stop et raccourci `Esc`.
- **Code editable** — retouche le script genere avant de l'envoyer a Blender.
- **Auto-run** — execution immediate apres la fin du streaming.
- **Boucle auto-fix** — sur erreur Blender, re-soumet automatiquement avec la traceback (configurable, 1 tentative par defaut).
- **Lint AST** avant envoi — les erreurs de syntaxe sont attrapees sans aller-retour Blender.
- **Render preview** — apres execution, l'addon rend le viewport et l'app affiche le PNG en ligne.
- **Stats par turn** — nombre de tokens prompt/reponse, duree, tokens/s.
- **Sauvegarde `.py`** par turn ; **export** de la conversation entiere en JSON.
- **Regeneration** (`↻`), **editer & re-soumettre** (`✎`), **copier** (`📋`) et **supprimer** (`🗑`) par turn.
- **Turns repliables** — clique sur l'en-tete d'une reponse pour replier/deplier.
- **Historique persistant** entre sessions (`~/.unification/history.json`), avec trimming automatique par budget de tokens.
- **Indicateur de budget tokens** — affiche `utilise / budget tok` en temps reel pres du prompt.
- **Routing dynamique du prompt** — prompt court lecture seule pour les requetes d'inspection (mots-cles : "lister", "combien", "affiche"…), prompt createur complet pour les requetes de construction.
- **Injection du contexte scene** — interroge Blender pour la liste d'objets avant chaque prompt, pour que le modele connaisse ce qui existe.
- **Coloration syntaxique** via Pygments, rendue directement dans la carte de turn.
- **Timestamp & badge de mode** sur chaque turn.
- **Support des modeles vision** — attache des images avec `qwen2.5-vl`, `llava`, `moondream`, `minicpm-v`, etc. Detection automatique depuis le nom du modele.

### Couche de fiabilite Blender
- **Wrap automatique `temp_override`** — chaque script s'execute dans un contexte `VIEW_3D` complet (window + screen + area + region + scene + view_layer). Plus d'erreurs `Operator … context is incorrect`.
- **Reset best-effort en mode `OBJECT`** avant execution — evite que le mode edition laisse par un script precedent casse les polls d'operateurs.
- **File d'execution serialisee** — les clics Run concurrents sont serialises pour ne pas creer de conflit sur le port TCP.
- **Retry TCP avec backoff exponentiel** — 3 tentatives sur `ConnectionRefusedError` (1 s → 2 s → 4 s).
- **Sanitizer AST au runtime** — reecrit silencieusement les cassures API connues de Blender 4.x :

| # | Ce qu'il detecte | Reecriture |
|---|---|---|
| 1 | `import bpy` / `import math` manquants | Auto-injection en tete de script |
| 2 | `bpy.ops.export_scene.obj(...)` | → `bpy.ops.wm.obj_export(...)` (supprime en 4.0) |
| 3 | `bpy.ops.import_scene.obj(...)` | → `bpy.ops.wm.obj_import(...)` (supprime en 4.0) |
| 4 | `light_add(type='HEMI')` | → `type='AREA'` (HEMI supprime) |
| 5 | `nodes["Principled BSDF"]` | → recherche par type `n.type == "BSDF_PRINCIPLED"` (independant de la locale) |
| 6 | `nodes["Geometry"]`, `nodes["Material Output"]`, etc. | → recherche par type pour 10 noms de noeuds courants (independant de la locale) |
| 7 | `mathutils.radians(...)` / `.degrees(...)` | → `math.radians(...)` / `math.degrees(...)` |
| 8 | `bpy.data.brushes.new(..., tool=X)` | Reecriture AST : supprime `tool=`, ajoute `brush.sculpt_tool = X`, corrige `tool=` → `mode=` |
| 9 | `subdivision_set(levels=N)` | → `subdivision_set(level=N)` (Blender attend `level`, singulier) |

---

## Demarrage rapide

### Option A — Executable Windows (aucun Python requis)

1. Telecharge `Unification.exe` depuis la derniere [GitHub Release](https://github.com/Oli97430/UNIFICATION/releases/latest).
2. Double-clique. Pas d'installateur, pas de venv.

### Option B — Depuis les sources (Windows / macOS / Linux)

```bash
git clone https://github.com/Oli97430/UNIFICATION.git
cd UNIFICATION
```

**Windows :**
```bat
run.bat
```

**macOS / Linux :**
```bash
chmod +x run.sh && ./run.sh
```

Ces scripts creent un environnement virtuel, installent les dependances et lancent l'app. Manuellement :

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate  |  macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Dependances

```
customtkinter>=5.2.2
Pillow>=10.0.0
Pygments>=2.17.0
requests>=2.31.0
```

Aucun SDK d'API payant — tout passe par Ollama en local.

### Checklist premier lancement

1. **Onglet Setup** → selectionne ton installation Blender → clique **Install / Update addon**.
2. Demarre Ollama : `ollama serve` (lance automatiquement sur Windows et macOS).
3. **Onglet Models** → selectionne `qwen2.5-coder:7b` → clique **Pull model** (~4,7 Go).
   Ou en CLI : `ollama pull qwen2.5-coder:7b`
4. **Dans Blender** : Edit → Preferences → Add-ons → cherche "MCP Server" → active-le. Demarre le serveur depuis la N-Panel du 3D Viewport.
5. De retour dans l'app, les deux pastilles (Ollama, Blender) doivent passer au vert.
6. Tape une requete dans l'onglet Chat et appuie sur `Ctrl+Entree`.

---

## Configuration des applis creatives

Chaque appli creative a besoin de son addon MCP en cours d'execution pour accepter les commandes TCP de UNIFICATION. Tous les addons partagent le meme protocole JSON + octet nul.

### Blender (port 9876)

L'addon Blender est installe automatiquement via l'**onglet Setup**. Alternativement :

1. Copie `assets/blender_mcp_addon.py` dans le dossier addons de Blender :
   - **Windows :** `%USERPROFILE%\AppData\Roaming\Blender Foundation\Blender\<X.Y>\scripts\addons\`
   - **macOS :** `~/Library/Application Support/Blender/<X.Y>/scripts/addons/`
   - **Linux :** `~/.config/blender/<X.Y>/scripts/addons/`
2. Dans Blender : Edit → Preferences → Add-ons → cherche "MCP Server" → active.
3. 3D Viewport → N-Panel → onglet MCP → **Start Server**.

La pastille de statut passe au vert une fois connecte.

### FreeCAD (port 9877)

1. Copie `assets/freecad_mcp_addon.py` dans le dossier Macro de FreeCAD :
   - **Windows :** `%APPDATA%\FreeCAD\Macro\`
   - **macOS :** `~/Library/Application Support/FreeCAD/Macro/`
   - **Linux :** `~/.local/share/FreeCAD/Macro/`
2. Dans FreeCAD : Macro → Macros → selectionne `freecad_mcp_addon` → **Executer**.
3. Ou depuis la console Python : `exec(open("chemin/vers/freecad_mcp_addon.py").read())`
4. Pour arreter : `from freecad_mcp_addon import server_stop; server_stop()`

### GIMP (port 9878)

**GIMP 2.10 :**
1. Copie `assets/gimp_mcp_addon.py` dans le dossier plug-ins :
   - **Windows :** `%APPDATA%\GIMP\2.10\plug-ins\`
   - **macOS :** `~/Library/Application Support/GIMP/2.10/plug-ins/`
   - **Linux :** `~/.config/GIMP/2.10/plug-ins/` (doit etre `chmod +x`)
2. Redemarre GIMP.
3. Filtres → Python-Fu → **MCP Server Start**.

**GIMP 3.0+ :**
1. Cree un sous-dossier : `~/.config/GIMP/3.0/plug-ins/gimp_mcp_addon/`
2. Copie `gimp_mcp_addon.py` dans ce sous-dossier (GIMP 3 exige que le nom du sous-dossier corresponde au nom du script).
3. Redemarre GIMP.
4. Filtres → **MCP Server Start**.

### Inkscape (port 9879)

Inkscape ne supporte pas les plugins persistants, cet addon tourne donc en **serveur standalone** a cote d'Inkscape :

```bash
pip install lxml            # requis
pip install inkex            # optionnel, pour les helpers inkex
python assets/inkscape_mcp_server.py --port 9879
```

Le serveur execute du code Python avec `lxml.etree`, `lxml.builder`, `inkex` (si disponible) pre-charges, et peut invoquer le CLI Inkscape pour le rendu et l'export.

### Photoshop (port 9880)

L'addon Photoshop tourne aussi en **serveur standalone** qui controle Photoshop via COM (Windows) ou AppleScript (macOS) :

**Windows :**
```bash
pip install pywin32
python assets/photoshop_mcp_server.py --port 9880
```

**macOS :**
```bash
python assets/photoshop_mcp_server.py --port 9880
```

Le serveur fournit un objet `ps` pre-charge (le bridge COM/AppleScript vers Photoshop) et supporte `DoJavaScript()` pour l'execution ExtendScript.

---

## Serveur MCP pour Claude Desktop / Cursor

UNIFICATION inclut un **serveur MCP unifie** (`mcp_server.py`) qui expose les 5 applis creatives a Claude Desktop, Cursor, ou tout client compatible MCP via stdio JSON-RPC 2.0.

### Configuration

Ajoute dans le fichier de config Claude Desktop (`claude_desktop_config.json`) :

```json
{
  "mcpServers": {
    "creative-suite": {
      "command": "python",
      "args": ["C:/chemin/vers/UNIFICATION/mcp_server.py"]
    }
  }
}
```

### Outils exposes

| Outil | Description |
|---|---|
| `execute_blender_code` | Envoie du code Python (`bpy`) a Blender sur le port 9876 |
| `execute_freecad_code` | Envoie du code Python (FreeCAD/Part/Draft) a FreeCAD sur le port 9877 |
| `execute_gimp_code` | Envoie du code Python-Fu a GIMP sur le port 9878 |
| `execute_inkscape_code` | Envoie du code Python (lxml/inkex) a Inkscape sur le port 9879 |
| `execute_photoshop_code` | Envoie du code Python/ExtendScript a Photoshop sur le port 9880 |
| `ping_all` | Verifie la connectivite des 5 applis d'un coup |
| `get_app_status` | Obtient les infos scene/document d'une appli specifique |

### Test

```bash
python mcp_server.py --test     # teste la connectivite de toutes les applis
python mcp_server.py --help     # affiche la documentation
```

---

## Modeles recommandes

> **Q4_K_M** — quantization 4 bits K-means, taille medium. Le meilleur compromis qualite/VRAM pour les modeles de code.

| Modele | VRAM | Notes |
|---|---|---|
| `qwen2.5:32b` | ~20 Go | **Defaut** — meilleure qualite globale pour le code `bpy` |
| `qwen2.5-coder:7b` | ~5 Go | Meilleur modele compact pour le code |
| `qwen2.5-coder:14b` | ~9 Go | Plus precis sur les taches multi-etapes complexes |
| `qwen2.5-coder:3b` | ~2 Go | GPU leger ou CPU uniquement |
| `deepseek-coder-v2:16b` | ~9 Go | Alternative tres solide |
| `codellama:13b` | ~7 Go | Le classique |
| `llama3.1:8b` | ~5 Go | Generaliste |
| `qwen2.5-vl:7b` *(vision)* | ~6 Go | Pour attacher des images au prompt |
| `qwen2.5-vl:32b` *(vision)* | ~20 Go | Meilleur modele vision pour 24 Go de VRAM |
| `llava:7b` *(vision)* | ~5 Go | Alternative vision |

Les modeles vision sont auto-detectes depuis le nom du modele (marqueurs : `vl`, `llava`, `vision`, `moondream`, `minicpm-v`). Quand un modele vision est selectionne, le bouton d'attachement d'image apparait dans la barre de chat.

---

## Architecture

```
                                    ┌─────────────────────────────────────────────────┐
                                    │            Applications creatives               │
┌──────────────────┐   prompt       │                                                 │
│   UNIFICATION    │ ──────────►    │  ┌──────────┐  Blender    (bpy)     port 9876   │
│   (cette app)    │   ┌────────┐   │  ├──────────┤  FreeCAD    (Part)    port 9877   │
│                  │──►│ Ollama │──►│  ├──────────┤  GIMP       (Py-Fu)   port 9878   │
│  customtkinter   │◄──│(local) │   │  ├──────────┤  Inkscape   (lxml)    port 9879   │
│  GUI + 6 onglets │   └────────┘   │  └──────────┘  Photoshop  (COM/AS)  port 9880   │
└──────────────────┘   tokens       └─────────────────────────────────────────────────┘
         ▲                                           │
         └────── stdout / result / render PNG ◄──────┘
```

```
┌─────────────────────────────────┐          ┌─────────────────────────────────┐
│  Claude Desktop / Cursor        │  stdio   │         mcp_server.py           │
│  (ou tout client MCP)           │◄────────►│  JSON-RPC 2.0  ·  7 outils     │
└─────────────────────────────────┘          │  → route vers ports 9876-9880   │
                                             └─────────────────────────────────┘
```

### Modules

| Module | Role |
|---|---|
| `main.py` | Point d'entree — ajoute la racine du projet au `sys.path`, appelle `gui.app.main()` |
| `core/ollama_client.py` | Client HTTP streaming (`/api/chat`, `/api/tags`), budget tokens, detection vision, extraction de code |
| `core/blender_client.py` | Client TCP, wrap `temp_override`, postamble render, sanitizer AST (7 regles de reecriture), retry exponentiel |
| `core/tcp_ping.py` | Ping TCP leger pour les addons FreeCAD / GIMP / Inkscape / Photoshop |
| `core/system_prompt.py` | Prompts createur & requete, regles Blender 4.x, routeur d'intention (`is_query_intent`) |
| `core/lint.py` | Lint pre-vol `ast.parse` + 5 avertissements patterns semantiques |
| `core/addon_installer.py` | Detection multi-OS des dossiers Blender (Win/macOS/Linux/Snap/Flatpak), telechargement GitHub, fallback hors-ligne |
| `core/updater.py` | Verification des releases GitHub (`tag_name` vs `APP_VERSION`) |
| `core/i18n.py` | Table de traductions EN / FR (~200 cles), detection auto locale OS, API `t(key)` |
| `core/settings.py` | Persistance JSON des reglages dans `~/.unification/settings.json` (20+ champs) |
| `gui/app.py` | Fenetre principale — sidebar avec Chat / Setup / Models / Settings / Logs / About, 6 pastilles de statut, selecteur de modele |
| `gui/chat_turn.py` | Carte de turn — animation streaming, CodeView editable, repliable, stats par turn, preview inline |
| `gui/widgets.py` | `CodeView` (Pygments), `StatusPill`, `Toast`, `Tooltip`, `InlineImage`, `IconButton` |
| `gui/theme.py` | Tokens de design (couleurs, polices, radii, scales) — dark/light/system |
| `mcp_server.py` | Serveur MCP unifie (stdio JSON-RPC 2.0) — 7 outils, route vers les 5 applis creatives |
| `assets/blender_mcp_addon.py` | Addon Blender N-Panel — serveur TCP sur port 9876, thread en arriere-plan, file d'execution main-thread |
| `assets/freecad_mcp_addon.py` | Plugin Macro FreeCAD — serveur TCP sur port 9877 |
| `assets/gimp_mcp_addon.py` | Plugin Python-Fu GIMP — serveur TCP sur port 9878 |
| `assets/inkscape_mcp_server.py` | Serveur standalone pour Inkscape — TCP sur port 9879, lxml/inkex + CLI |
| `assets/photoshop_mcp_server.py` | Serveur standalone pour Photoshop — TCP sur port 9880, COM (Win) / AppleScript (macOS) |

---

## Protocole TCP

Les 5 addons partagent le meme framing : **JSON + octet nul (`\0`)** sur TCP brut.

### Requete

```json
{"type": "execute", "code": "import bpy\nbpy.ops.mesh.primitive_cube_add()"}
```

Suivi d'un octet `\0`.

### Reponse

```json
{"status": "ok", "result": "Cube created", "stdout": "..."}
```

Ou en cas d'erreur :

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

Tous bindent sur `127.0.0.1` (localhost uniquement). Timeout par defaut : 30 secondes.

---

## Raccourcis clavier

| Action | Raccourci |
|---|---|
| Envoyer le prompt | `Ctrl+Entree` |
| Arreter le streaming | `Echap` |
| Vider la conversation | `Ctrl+L` |
| Focus sur le champ de prompt | `Ctrl+K` |
| Ouvrir les reglages | `Ctrl+,` |
| Onglets Chat / Setup / Models / Logs | `Ctrl+1` / `Ctrl+2` / `Ctrl+3` / `Ctrl+4` |

---

## Reglages

Tous les reglages se trouvent dans l'**onglet Settings** et persistent dans `~/.unification/settings.json` :

| Section | Option | Defaut | Description |
|---|---|---|---|
| **Ollama** | URL de l'endpoint | `http://localhost:11434` | URL de base de l'API Ollama |
| | Temperature | `0.2` | Plus bas = plus deterministe |
| | Keep-alive | `5m` | Duree pendant laquelle Ollama garde le modele en memoire |
| **Blender** | Host | `127.0.0.1` | Host TCP pour tous les addons |
| | Port | `9876` | Port de l'addon Blender |
| | Test de connexion | — | Bouton de ping manuel |
| **Behaviour** | Historique persistant | `true` | Sauvegarde la conversation dans `history.json` |
| | Routing auto du prompt | `true` | Prompt court pour les requetes, prompt complet pour la creation |
| | Injection contexte scene | `true` | Interroge Blender pour la liste d'objets avant chaque prompt |
| | Verif. mises a jour | `true` | Verification silencieuse des GitHub Releases au demarrage |
| | Fenetre de contexte (num_ctx) | `8192` | Taille de la fenetre de contexte Ollama |
| | Budget tokens max | `8000` | Budget de tokens pour l'historique de conversation |
| | Tentatives auto-fix | `1` | Nombre max de re-prompts sur erreur (0 = desactive) |
| **Appearance** | Theme | `dark` | Dark / Light / System |
| | Langue | `auto` | Auto (locale OS) / English / Francais |

Toggles inline dans la barre de chat :

| Toggle | Defaut | Effet |
|---|---|---|
| **Auto-run** | on | Execute le code immediatement apres le streaming |
| **Auto-fix** | on | Re-soumet au modele en cas d'erreur Blender |
| **Preview** | off | Rend le viewport apres execution |

---

## Fichiers utilisateur

Tout est stocke sous `~/.unification/` — pas de registre, pas de dossiers caches ailleurs.

```
~/.unification/
├── settings.json     # reglages persistants (20+ champs)
├── history.json      # historique des conversations (si active)
└── events.log        # journal des evenements (visible dans l'onglet Logs)
```

Aucune telemetrie. Aucun appel reseau en dehors de l'instance Ollama locale et de l'API GitHub Releases (verification de mise a jour, desactivable dans Settings).

---

## Troubleshooting

### General

| Symptome | Solution |
|---|---|
| L'app ne demarre pas | Lance `python main.py` dans un terminal pour voir la traceback. Verifie `pip install -r requirements.txt`. |
| Le modele hallucine sur l'API `bpy` | Utilise `qwen2.5-coder:7b` ou `:14b`. Baisse la temperature a `0.1`. |
| Conversation trop lente | Reduis **Max history tokens** dans Settings ou efface avec `Ctrl+L`. |

### Ollama

| Symptome | Solution |
|---|---|
| Pastille **Ollama** reste rouge | Lance `ollama serve`, ou verifie l'URL dans Settings. |

### Blender

| Symptome | Solution |
|---|---|
| Pastille **Blender** reste rouge | L'addon n'est pas demarre. Onglet Setup → Install. Puis dans Blender : Edit → Preferences → Add-ons → "MCP Server" → Activer. N-Panel → MCP → Start Server. |
| `Operator … context is incorrect` | Gere automatiquement par le wrap VIEW_3D. Si ca persiste, consulte l'onglet Logs. |
| `KeyError: 'Principled BSDF'` | Regenere le turn (`↻`). Le system prompt enseigne le pattern BSDF robuste. Le sanitizer corrige aussi automatiquement. |
| `TypeError: brushes.new() tool=…` | Corrige par le sanitizer AST depuis la v1.1.2. Mets a jour l'app. |
| `import_scene.obj` / `export_scene.obj` introuvable | Corrige automatiquement — le sanitizer reecrit vers `wm.obj_import` / `wm.obj_export`. |
| `mathutils.radians` / `mathutils.degrees` | Corrige automatiquement — reecrit en `math.radians` / `math.degrees`. |

### FreeCAD

| Symptome | Solution |
|---|---|
| Pastille **FreeCAD** reste rouge | Assure-toi que la macro tourne. Dans FreeCAD : Macro → Macros → `freecad_mcp_addon` → Executer. |
| Macro introuvable | Copie `assets/freecad_mcp_addon.py` dans `%APPDATA%\FreeCAD\Macro\` (Windows) ou `~/.local/share/FreeCAD/Macro/` (Linux). |

### GIMP

| Symptome | Solution |
|---|---|
| Pastille **GIMP** reste rouge | Filtres → Python-Fu → MCP Server Start. Si l'entree de menu n'existe pas, le plugin n'est pas installe correctement. |
| Plugin invisible dans les menus | GIMP 2.10 : verifie les permissions (`chmod +x` sur Linux/macOS). GIMP 3.0+ : le script doit etre dans un sous-dossier du meme nom. |

### Inkscape

| Symptome | Solution |
|---|---|
| Pastille **Inkscape** reste rouge | Le serveur standalone ne tourne pas. Lance `python assets/inkscape_mcp_server.py`. |
| `lxml` introuvable | `pip install lxml` — requis pour le serveur Inkscape. |

### Photoshop

| Symptome | Solution |
|---|---|
| Pastille **Photoshop** reste rouge | Le serveur standalone ne tourne pas. Lance `python assets/photoshop_mcp_server.py`. |
| Erreur COM (Windows) | `pip install pywin32`. Assure-toi que Photoshop est ouvert. |
| Erreur AppleScript (macOS) | Accorde l'acces automatisation a Terminal / Python dans Reglages systeme → Confidentialite et securite. |

---

## Build & release

### Construire l'exe Windows

```bat
build.bat
```

Produit `dist\Unification.exe` (single-file, windowed, icone personnalisee, ~21 Mo). Sur macOS / Linux :

```bash
./build.sh
```

Le build embarque : tous les fichiers d'addon (Blender, FreeCAD, GIMP, Inkscape, Photoshop), `mcp_server.py`, les assets logo, et les donnees de theme customtkinter.

### Regenerer le logo

```bash
python assets/make_logo.py
```

Genere `logo.png` (512 px), `logo_128.png`, `logo_64.png`, `logo_32.png`, et `logo.ico` (multi-taille). Le logo est une silhouette de profil d'Einstein — un clin d'oeil a la theorie du champ unifie qui a inspire le nom de l'app.

### Publier une release

```bash
git tag -a v2.x.y -m "v2.x.y — description"
git push origin main && git push origin v2.x.y

gh release create v2.x.y dist/Unification.exe \
    --title "v2.x.y — Description courte" \
    --notes "Changelog ici"
```

Le verificateur de mise a jour integre interroge `https://api.github.com/repos/Oli97430/UNIFICATION/releases/latest` et compare le `tag_name` avec `APP_VERSION` dans `gui/app.py`. Si une version plus recente existe → toast avec lien vers la release.

---

## Licence

[GPL-3.0-or-later](LICENSE) — pour rester compatible avec le blender-mcp-addon et l'ecosysteme Blender upstream.
