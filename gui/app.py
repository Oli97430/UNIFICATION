"""Main OllamaToBlender window — sidebar + content router."""
from __future__ import annotations

import base64
import io
import re
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Any

from PIL import Image as PILImage

import customtkinter as ctk
from PIL import Image

from core import (
    ADDON_REMOTE_URL,
    BlenderAddonDir,
    BlenderClient,
    OllamaClient,
    Settings,
    StreamStats,
    SYSTEM_PROMPT,
    UpdateInfo,
    check_for_update,
    find_blender_addon_dirs,
    install_addon,
    lint_python,
    load_history,
    model_supports_vision,
    open_addon_dir,
    pick_system_prompt,
    read_bundled_version,
    save_history,
    trim_history,
    uninstall_addon,
)
from core.ollama_client import RECOMMENDED_MODELS, extract_python_code
from core.settings import LOG_PATH

from . import theme as T
from .chat_turn import ChatTurn
from .widgets import IconButton, SidebarButton, StatusPill, Toast, attach_tooltip


ASSETS = Path(__file__).resolve().parent.parent / "assets"


class OllamaToBlenderApp(ctk.CTk):
    APP_TITLE = "OllamaToBlender"
    APP_VERSION = "1.0.3"

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()

        ctk.set_appearance_mode(self.settings.appearance_mode)
        ctk.set_default_color_theme("blue")

        self.title(self.APP_TITLE)
        self.minsize(1100, 720)
        if self.settings.window_geometry:
            try:
                self.geometry(self.settings.window_geometry)
            except tk.TclError:
                self.geometry("1380x900")
        else:
            self.geometry("1380x900")
        self.configure(fg_color=T.BG_BASE)
        self._set_window_icon()

        self.ollama = OllamaClient(self.settings.ollama_url)
        self.blender = BlenderClient(self.settings.blender_host, self.settings.blender_port)

        self._views: dict[str, ctk.CTkFrame] = {}
        self._sidebar_btns: dict[str, SidebarButton] = {}
        self._current_view: str = "chat"
        self._chat_turns: list[ChatTurn] = []
        self._convo_history: list[dict] = []  # {role, content}
        self._stop_event: threading.Event | None = None
        self._active_turn: ChatTurn | None = None

        self._image_refs: list[Any] = []  # keep PhotoImage refs alive
        self._log_lines: list[str] = []
        self._attached_image_b64: str | None = None
        self._attached_image_thumb: ctk.CTkImage | None = None

        self._build_layout()
        self.show_view("chat")
        self._wire_shortcuts()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._refresh_status)
        self.after(2000, self._poll_status_loop)

        if self.settings.persist_history:
            self.after(50, self._restore_history)

        if self.settings.check_for_updates:
            self.after(2500, self._check_updates_async)

        self._log("app started")

    def _check_updates_async(self) -> None:
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self) -> None:
        info: UpdateInfo | None = check_for_update(self.APP_VERSION)
        if info is None or not info.available:
            return
        self.after(0, lambda: Toast(
            self,
            f"Update available: v{info.latest}  ·  click About",
            kind="info",
            duration_ms=5000,
        ))
        self.after(0, lambda: self._log(f"update available: v{info.latest}  →  {info.url}"))
        self._latest_update_info = info

    # =========================================================== chrome

    def _set_window_icon(self) -> None:
        ico = ASSETS / "logo.ico"
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass

    def _ctk_image(self, path: Path, size: tuple[int, int]) -> ctk.CTkImage | None:
        try:
            img = ctk.CTkImage(light_image=Image.open(path), dark_image=Image.open(path), size=size)
            self._image_refs.append(img)
            return img
        except Exception:
            return None

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color=T.BG_BASE, corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew", padx=(0, 16), pady=(8, 16))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._build_chat_view()
        self._build_setup_view()
        self._build_models_view()
        self._build_settings_view()
        self._build_logs_view()
        self._build_about_view()

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=T.BG_BASE, height=64, corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))
        bar.grid_columnconfigure(2, weight=1)

        img = self._ctk_image(ASSETS / "logo.png", (44, 44))
        if img:
            ctk.CTkLabel(bar, image=img, text="").grid(row=0, column=0, padx=(2, 10))

        ctk.CTkLabel(
            bar, text=self.APP_TITLE, text_color=T.INK, font=(T.FONT_FAMILY, 22, "bold")
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            bar,
            text="   ·  Local-LLM bridge for Blender",
            text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 13),
        ).grid(row=0, column=2, sticky="w")

        pills = ctk.CTkFrame(bar, fg_color="transparent")
        pills.grid(row=0, column=3, sticky="e")
        self.pill_ollama = StatusPill(pills, "Ollama")
        self.pill_ollama.pack(side="left", padx=(0, 6))
        attach_tooltip(self.pill_ollama, "Click to refresh status")
        self.pill_ollama.bind("<Button-1>", lambda _e: self._refresh_status())
        self.pill_blender = StatusPill(pills, "Blender")
        self.pill_blender.pack(side="left")
        attach_tooltip(self.pill_blender, "Click to ping the Blender addon")
        self.pill_blender.bind("<Button-1>", lambda _e: self._refresh_status())

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color=T.BG_PANEL, width=260, corner_radius=T.R_LG)
        side.grid(row=1, column=0, sticky="ns", padx=(16, 12), pady=(8, 16))
        side.grid_propagate(False)

        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(14, 10))

        items = [
            ("chat", "Chat", "💬", "Ctrl+1"),
            ("setup", "Setup", "🧩", "Ctrl+2"),
            ("models", "Models", "📦", "Ctrl+3"),
            ("settings", "Settings", "⚙", "Ctrl+,"),
            ("logs", "Logs", "📜", "Ctrl+4"),
            ("about", "About", "ⓘ", ""),
        ]
        for key, label, icon, accel in items:
            btn = SidebarButton(nav, text=label, icon=icon, command=lambda k=key: self.show_view(k))
            btn.pack(fill="x", pady=2)
            if accel:
                attach_tooltip(btn, f"{label}  ({accel})")
            self._sidebar_btns[key] = btn

        # Footer with model selector
        footer = ctk.CTkFrame(side, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=10, pady=(8, 14))
        ctk.CTkLabel(footer, text="MODEL", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 11, "bold")).pack(anchor="w")
        self.model_combo = ctk.CTkComboBox(
            footer,
            values=[self.settings.ollama_model],
            command=self._on_model_changed,
            width=210,
            fg_color=T.BG_INPUT,
            button_color=T.BG_RAISED,
            button_hover_color=T.BG_RAISED,
            border_color=T.EDGE,
            text_color=T.INK,
            dropdown_fg_color=T.BG_RAISED,
            dropdown_text_color=T.INK,
            font=(T.FONT_FAMILY, 13),
        )
        self.model_combo.set(self.settings.ollama_model)
        self.model_combo.pack(fill="x", pady=(4, 0))
        attach_tooltip(self.model_combo, "Active Ollama model — change anytime")

    # =========================================================== view router

    def show_view(self, name: str) -> None:
        for v in self._views.values():
            v.grid_remove()
        self._views[name].grid(row=0, column=0, sticky="nsew")
        self._current_view = name
        for k, b in self._sidebar_btns.items():
            b.set_active(k == name)
        if name == "models":
            self._refresh_models_list()
        if name == "setup":
            self._refresh_addon_dirs()
        if name == "logs":
            self._refresh_logs_view()
        if name == "chat":
            try:
                self.prompt_entry.focus_set()
            except Exception:
                pass

    # =========================================================== chat view

    def _build_chat_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)
        self._views["chat"] = view

        self.history_frame = ctk.CTkScrollableFrame(
            view,
            fg_color="transparent",
            scrollbar_button_color=T.BG_RAISED,
            scrollbar_button_hover_color=T.EDGE,
        )
        self.history_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=(0, 8))

        self._build_empty_state()

        # Input area
        input_card = ctk.CTkFrame(
            view,
            fg_color=T.BG_PANEL,
            corner_radius=T.R_LG,
            border_width=1,
            border_color=T.EDGE,
        )
        input_card.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 8))

        self.prompt_entry = ctk.CTkTextbox(
            input_card,
            height=96,
            fg_color="transparent",
            text_color=T.INK,
            border_width=0,
            font=(T.FONT_FAMILY, 15),
            wrap="word",
        )
        self.prompt_entry.pack(fill="x", padx=14, pady=(12, 6))
        self.prompt_entry.bind("<Control-Return>", self._on_send)
        self.prompt_entry.bind("<KeyPress>", self._clear_placeholder, add="+")
        self._placeholder_active = True
        self._set_placeholder()

        self._ctrl_row = ctk.CTkFrame(input_card, fg_color="transparent")
        ctrl = self._ctrl_row
        ctrl.pack(fill="x", padx=14, pady=(0, 10))

        self.auto_run_var = ctk.BooleanVar(value=self.settings.auto_execute)
        auto_chk = ctk.CTkCheckBox(
            ctrl,
            text="Auto-run",
            variable=self.auto_run_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        auto_chk.pack(side="left")
        attach_tooltip(auto_chk, "Run the generated code immediately after streaming ends")

        self.auto_fix_var = ctk.BooleanVar(value=self.settings.auto_fix_on_error)
        fix_chk = ctk.CTkCheckBox(
            ctrl,
            text="Auto-fix",
            variable=self.auto_fix_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        fix_chk.pack(side="left", padx=(12, 0))
        attach_tooltip(fix_chk, "If Blender returns an error, ask the model to fix it automatically")

        self.render_var = ctk.BooleanVar(value=self.settings.auto_render_preview)
        render_chk = ctk.CTkCheckBox(
            ctrl,
            text="Preview",
            variable=self.render_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        render_chk.pack(side="left", padx=(12, 0))
        attach_tooltip(render_chk, "Render a viewport preview after each run and show it inline")

        ctk.CTkLabel(
            ctrl, text="Ctrl+Enter to send", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)
        ).pack(side="left", padx=(16, 0))

        self.export_btn = IconButton(
            ctrl, text="Export", command=self._export_conversation,
            tooltip="Save the whole conversation as JSON", width=84,
        )
        self.export_btn.pack(side="right", padx=(8, 0))

        self.clear_btn = IconButton(
            ctrl, text="Clear", command=self._clear_chat,
            tooltip="Clear all turns  (Ctrl+L)", width=82,
        )
        self.clear_btn.pack(side="right", padx=(8, 0))

        self.send_btn = ctk.CTkButton(
            ctrl,
            text="Send  ⏎",
            width=130,
            height=36,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_send,
        )
        self.send_btn.pack(side="right")
        attach_tooltip(self.send_btn, "Send (Ctrl+Enter)")

        self.attach_btn = IconButton(
            ctrl, text="📎", command=self._on_attach_image,
            tooltip="Attach an image (vision-capable models only)", width=40,
        )
        self.attach_btn.pack(side="right", padx=(0, 6))
        self._refresh_attach_visibility()

        # Thumbnail row (only visible when an image is attached)
        self.attach_row = ctk.CTkFrame(input_card, fg_color="transparent")
        self.attach_thumb_label = ctk.CTkLabel(self.attach_row, text="", text_color=T.INK_MUTED)
        self.attach_thumb_label.pack(side="left", padx=(14, 8), pady=(0, 8))
        self.attach_filename_label = ctk.CTkLabel(
            self.attach_row, text="", text_color=T.INK_DIM, font=(T.FONT_MONO, 11),
        )
        self.attach_filename_label.pack(side="left", pady=(0, 8))
        IconButton(
            self.attach_row, text="✕  remove", command=self._clear_attached_image,
            tooltip="Remove this attachment", width=110,
        ).pack(side="right", padx=(0, 14), pady=(0, 8))

    def _build_empty_state(self) -> None:
        self.empty_state = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        self.empty_state.pack(fill="x", pady=80)

        big = self._ctk_image(ASSETS / "logo.png", (120, 120))
        if big:
            ctk.CTkLabel(self.empty_state, image=big, text="").pack()

        ctk.CTkLabel(
            self.empty_state,
            text="OllamaToBlender",
            text_color=T.INK,
            font=(T.FONT_FAMILY, 26, "bold"),
        ).pack(pady=(14, 4))

        ctk.CTkLabel(
            self.empty_state,
            text="Describe what you want to build in Blender.\nOllama generates the bpy code, the addon runs it.",
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 14),
            justify="center",
        ).pack()

        suggestions = [
            # Build / shading — covers materials + lighting + multi-object composition
            "Build a stylised studio scene: a wood floor, a glass icosphere, and a 3-point lighting rig",
            # Animation — covers keyframes + procedural motion
            "Make a 48-frame seamless looping animation of a metallic torus orbiting a sun lamp",
            # Procedural generation — shows the bpy.data muscle
            "Generate a procedural low-poly forest: 12 trees with random heights on a 20×20 ground plane",
            # Inspection — triggers the short query system prompt
            "List every object in the scene with its type, vertex count, and material names",
            # Render hook — pairs with the Preview toggle
            "Set up a soft golden-hour sun, then render a 720p preview from the camera",
            # Cleanup — uses the data-API path the system prompt now teaches
            "Wipe the scene, then add a single Suzanne with a brushed-copper Principled BSDF material",
            # Low-level modeling with bmesh
            "Use bmesh to build a custom hex-grid floor (8×8 cells, hex radius 0.5) centred at origin",
            # Camera setup + procedural orbit animation
            "Add a 35mm camera 8 m from origin and animate a 120-frame turntable around the active object",
            # Modifier stack composition
            "Apply Subdivision (viewport level 3), Bevel (width 0.04), then Wireframe to the active mesh",
            # Physics simulation — rigid body
            "Drop 20 random-coloured cubes onto a passive ground plane with rigid body physics over 60 frames",
            # Particle / scatter system
            "Scatter 200 small icospheres across the surface of the active mesh with a hair particle system",
            # Filesystem / batch export
            "Export every visible mesh to a separate .obj file under a new 'export/' folder next to the .blend",
        ]
        sug_frame = ctk.CTkFrame(self.empty_state, fg_color="transparent")
        sug_frame.pack(pady=24)
        for i, s in enumerate(suggestions):
            r, c = divmod(i, 2)
            chip = ctk.CTkButton(
                sug_frame,
                text=s,
                width=340,
                height=52,
                fg_color=T.BG_PANEL,
                hover_color=T.BG_RAISED,
                text_color=T.INK_MUTED,
                border_width=1,
                border_color=T.EDGE,
                font=(T.FONT_FAMILY, 13),
                anchor="w",
                command=lambda t=s: self._insert_prompt(t),
            )
            chip.grid(row=r, column=c, padx=6, pady=4)

    def _insert_prompt(self, text: str) -> None:
        self._clear_placeholder()
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.insert("1.0", text)
        self.prompt_entry.focus_set()

    def _set_placeholder(self) -> None:
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.insert(
            "1.0",
            "Describe a Blender task…   (e.g. add a glass sphere on a wood plane)",
        )
        self.prompt_entry.configure(text_color=T.INK_DIM)
        self._placeholder_active = True

    def _clear_placeholder(self, _evt=None) -> None:
        if not self._placeholder_active:
            return
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.configure(text_color=T.INK)
        self._placeholder_active = False

    # ----- chat actions ------------------------------------------------------

    def _on_send(self, _evt=None) -> str:
        if self._placeholder_active:
            return "break"
        text = self.prompt_entry.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        self.prompt_entry.delete("1.0", "end")
        self._set_placeholder()
        if self.empty_state and self.empty_state.winfo_exists():
            self.empty_state.destroy()
        attached = self._attached_image_b64
        self._clear_attached_image()
        self._submit_prompt(text, image_b64=attached)
        return "break"

    def _submit_prompt(self, text: str, replay: bool = False, *, image_b64: str | None = None,
                        is_auto_fix: bool = False, fix_attempt: int = 0) -> None:
        self.send_btn.configure(state="disabled", text="…")

        display_prompt = text if not is_auto_fix else f"(auto-fix attempt {fix_attempt})"

        turn = ChatTurn(
            self.history_frame,
            prompt=display_prompt,
            model_name=self.settings.ollama_model,
            on_run=self._on_run_turn,
            on_retry=self._on_retry_turn,
            on_stop=self._on_stop_turn,
            image_b64=image_b64,
        )
        turn._fix_attempts = fix_attempt  # type: ignore[attr-defined]
        turn.pack(fill="x", pady=(2, 0))
        self._chat_turns.append(turn)
        if not replay:
            user_msg: dict[str, Any] = {"role": "user", "content": text}
            if image_b64:
                user_msg["images"] = [image_b64]
            self._convo_history.append(user_msg)
        self._scroll_to_bottom()

        stop_event = threading.Event()
        self._stop_event = stop_event
        self._active_turn = turn
        stats = StreamStats()
        turn.start_streaming(stats)
        threading.Thread(
            target=self._stream_into_turn,
            args=(turn, stop_event, stats, text),
            daemon=True,
        ).start()

    def _stream_into_turn(
        self,
        turn: ChatTurn,
        stop_event: threading.Event,
        stats: StreamStats,
        user_msg: str,
    ) -> None:
        full: list[str] = []
        # Pick the appropriate system prompt (creator vs query)
        sys_prompt = pick_system_prompt(user_msg) if self.settings.auto_route_prompt else SYSTEM_PROMPT
        # Trim history down to the configured token budget
        kept, dropped = trim_history(
            self._convo_history,
            max_tokens=max(1024, self.settings.max_history_tokens),
            keep_last=6,
        )
        if dropped:
            self._log(f"history trimmed: dropped {len(dropped)} message(s) for budget")
        messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}, *kept]
        try:
            for token in self.ollama.chat_stream(
                model=self.settings.ollama_model,
                messages=messages,
                temperature=self.settings.temperature,
                keep_alive=self.settings.keep_alive,
                stop_event=stop_event,
                stats=stats,
            ):
                full.append(token)
                self.after(0, turn.append_response, token)
                self.after(0, self._scroll_to_bottom_smooth)
        except Exception as exc:
            self.after(0, turn.set_error, f"Ollama error: {exc}")
            self.after(0, lambda: self.send_btn.configure(state="normal", text="Send  ⏎"))
            self.after(0, lambda: self._log(f"ollama error: {exc}"))
            self.after(0, self._mark_idle)
            return

        full_text = "".join(full)
        code = extract_python_code(full_text)
        if not stats.aborted:
            self._convo_history.append({"role": "assistant", "content": full_text})
        self.after(0, turn.finish_response, full_text, code, stats)
        self.after(0, lambda: self.send_btn.configure(state="normal", text="Send  ⏎"))
        self.after(0, self._mark_idle)
        self.after(0, lambda: self._log(
            f"stream done: {stats.response_tokens} tok in {stats.elapsed_s:.1f}s"
            f"{' (aborted)' if stats.aborted else ''}"
        ))

        if (
            self.auto_run_var.get()
            and code.strip()
            and not stats.aborted
        ):
            self.after(120, self._on_run_turn, turn)

    def _mark_idle(self) -> None:
        self._stop_event = None
        self._active_turn = None
        self._save_history_async()

    def _on_run_turn(self, turn: ChatTurn) -> None:
        code = turn.code_view.get_code() if turn.code else ""
        if not code.strip():
            return
        turn.set_blender_running()
        threading.Thread(target=self._exec_in_blender, args=(turn, code), daemon=True).start()

    def _exec_in_blender(self, turn: ChatTurn, code: str) -> None:
        # Pre-flight lint — catch syntax errors before paying a Blender round-trip
        issues = lint_python(code)
        if issues:
            msg = "Syntax check failed:\n" + "\n".join(i.format() for i in issues)
            payload = {"result": None, "stdout": "", "message": msg}
            self.after(0, turn.set_blender_result, "error", payload)
            self.after(0, lambda: self._log(f"lint failure: {msg}"))
            self.after(0, lambda: self._maybe_auto_fix(turn, msg))
            return
        result = self.blender.execute(
            code,
            timeout=120.0,
            with_render=bool(self.render_var.get()) if hasattr(self, "render_var") else False,
        )
        payload = {"result": result.result, "stdout": result.stdout, "message": result.message}
        self.after(0, turn.set_blender_result, result.status, payload)
        self.after(0, self._refresh_blender_status)
        self.after(0, lambda: self._log(f"blender: {result.status}"))
        self.after(0, self._save_history_async)
        if result.status in ("error", "transport_error") and result.message:
            self.after(0, lambda: self._maybe_auto_fix(turn, result.message))

    def _maybe_auto_fix(self, turn: ChatTurn, error_text: str) -> None:
        """Spawn an auto-fix turn that asks the model to repair the failing code."""
        if not self.auto_fix_var.get():
            return
        attempts = getattr(turn, "_fix_attempts", 0)
        if attempts >= max(0, self.settings.max_fix_attempts):
            self._log(f"auto-fix budget exhausted ({attempts}/{self.settings.max_fix_attempts})")
            return
        last_code = turn.code_view.get_code() if turn.code else ""
        # Trim very long tracebacks to keep the prompt focused
        snippet = error_text.strip()
        if len(snippet) > 1500:
            snippet = snippet[-1500:]
        text = (
            "The Python code you produced raised an error when executed in Blender. "
            "Read the traceback below carefully and reply with a CORRECTED full script "
            "(one ```python``` block, no prose). Keep the original intent.\n\n"
            f"--- previous code ---\n{last_code}\n\n"
            f"--- traceback ---\n{snippet}"
        )
        self._submit_prompt(text, is_auto_fix=True, fix_attempt=attempts + 1)

    def _on_retry_turn(self, turn: ChatTurn) -> None:
        idx = self._chat_turns.index(turn)
        if self._convo_history and self._convo_history[-1]["role"] == "assistant":
            self._convo_history.pop()
        prompt = turn.prompt
        turn.destroy()
        self._chat_turns.pop(idx)
        # remove the user message that this turn consumed
        for i in range(len(self._convo_history) - 1, -1, -1):
            if (
                self._convo_history[i]["role"] == "user"
                and self._convo_history[i]["content"] == prompt
            ):
                self._convo_history.pop(i)
                break
        self._submit_prompt(prompt)

    def _on_stop_turn(self, _turn: ChatTurn) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
            self._log("user stopped streaming")

    def _clear_chat(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        for t in self._chat_turns:
            try:
                t.destroy()
            except Exception:
                pass
        self._chat_turns.clear()
        self._convo_history.clear()
        self._build_empty_state()
        self._save_history_async()

    def _scroll_to_bottom(self) -> None:
        try:
            self.history_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _scroll_to_bottom_smooth(self) -> None:
        # only auto-scroll if the user hasn't scrolled up significantly
        try:
            top, bottom = self.history_frame._parent_canvas.yview()
            if bottom > 0.92:
                self.history_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _export_conversation(self) -> None:
        if not self._chat_turns:
            Toast(self, "Nothing to export", kind="warn")
            return
        path = filedialog.asksaveasfilename(
            title="Export conversation",
            defaultextension=".json",
            initialfile=f"ollamatoblender_{datetime.now():%Y%m%d_%H%M%S}.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        save_history([t.to_dict() for t in self._chat_turns], Path(path))
        Toast(self, "Exported", kind="ok")

    # =========================================================== setup view

    def _build_setup_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)
        self._views["setup"] = view

        # ----- header
        ctk.CTkLabel(view, text="Setup", text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )
        ctk.CTkLabel(
            view,
            text=(
                "OllamaToBlender talks to Blender through the blender-mcp-addon "
                "(a tiny TCP server, port 9876).  Install it once per Blender version, "
                "then enable it from Edit → Preferences → Add-ons."
            ),
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 13),
            justify="left",
            wraplength=1020,
        ).grid(row=1, column=0, sticky="w", padx=4, pady=(0, 12))

        # ----- body grid: detected dirs (left) + actions (right)
        body = ctk.CTkFrame(view, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Left: detected installs
        left = ctk.CTkFrame(
            body, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        head = ctk.CTkFrame(left, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(head, text="Detected Blender installs", text_color=T.INK,
                     font=(T.FONT_FAMILY, 15, "bold")).pack(side="left")
        IconButton(head, text="Refresh", command=self._refresh_addon_dirs, width=84).pack(side="right")

        ctk.CTkLabel(
            left,
            text=f"Bundled addon: v{read_bundled_version() or '?'}",
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        ).pack(anchor="w", padx=14)

        self.addon_dirs_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.addon_dirs_frame.pack(fill="both", expand=True, padx=8, pady=(8, 12))

        self._addon_selected = ctk.StringVar(value="")
        self._addon_dirs: list[BlenderAddonDir] = []

        # Manual path
        manual = ctk.CTkFrame(left, fg_color="transparent")
        manual.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(manual, text="Custom path", text_color=T.INK_MUTED,
                     font=(T.FONT_FAMILY, 12)).pack(anchor="w")
        manual_row = ctk.CTkFrame(manual, fg_color="transparent")
        manual_row.pack(fill="x", pady=(2, 0))
        self.addon_manual_entry = ctk.CTkEntry(
            manual_row,
            placeholder_text=r"e.g. C:\Users\<you>\AppData\Roaming\Blender Foundation\Blender\4.5\scripts\addons",
            fg_color=T.BG_INPUT, border_color=T.EDGE, text_color=T.INK,
            font=(T.FONT_MONO, 12),
        )
        self.addon_manual_entry.pack(side="left", fill="x", expand=True)
        IconButton(manual_row, text="Browse", command=self._pick_addon_dir,
                   tooltip="Pick a Blender addons directory", width=82
                   ).pack(side="left", padx=(6, 0))
        IconButton(manual_row, text="Use", command=self._add_manual_addon_dir,
                   tooltip="Add this folder to the list", width=72
                   ).pack(side="left", padx=(6, 0))

        # Right: source + actions
        right = ctk.CTkFrame(
            body, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(right, text="Install source", text_color=T.INK,
                     font=(T.FONT_FAMILY, 15, "bold")).pack(anchor="w", padx=14, pady=(12, 4))

        self._addon_source = ctk.StringVar(value="remote")
        for val, label, tip in [
            ("remote", "Latest from GitHub", f"GET {ADDON_REMOTE_URL}"),
            ("bundled", "Bundled (offline)", "Use the .py shipped inside this app"),
        ]:
            rb = ctk.CTkRadioButton(
                right, text=label, value=val, variable=self._addon_source,
                fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.EDGE,
                text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13),
            )
            rb.pack(anchor="w", padx=14, pady=2)
            attach_tooltip(rb, tip)

        ctk.CTkLabel(right, text="", height=4).pack()  # spacer

        self.btn_install = ctk.CTkButton(
            right,
            text="⬇  Install / Update addon",
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_install_addon, state="disabled",
        )
        self.btn_install.pack(fill="x", padx=14, pady=(2, 6))

        self.btn_open_dir = IconButton(
            right, text="📂  Open folder", command=self._on_open_addon_dir,
            tooltip="Reveal the addons folder in your file explorer",
            width=210, height=38,
        )
        self.btn_open_dir.configure(state="disabled")
        self.btn_open_dir.pack(fill="x", padx=14, pady=(0, 4))

        self.btn_uninstall = IconButton(
            right, text="🗑  Uninstall", command=self._on_uninstall_addon,
            tooltip="Remove the addon from the selected directory",
            width=210, height=38,
        )
        self.btn_uninstall.configure(state="disabled")
        self.btn_uninstall.pack(fill="x", padx=14, pady=(0, 12))

        self.addon_status_label = ctk.CTkLabel(
            right, text="Select a directory above.", text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 13), wraplength=380, justify="left",
        )
        self.addon_status_label.pack(anchor="w", padx=14, pady=(0, 12))

        # Next steps
        ctk.CTkLabel(right, text="After installing", text_color=T.INK,
                     font=(T.FONT_FAMILY, 15, "bold")).pack(anchor="w", padx=14, pady=(2, 4))
        for step in (
            "1.  Open Blender",
            "2.  Edit → Preferences → Add-ons",
            "3.  Search “MCP Server”, tick the checkbox",
            "4.  3D Viewport → N-Panel → MCP",
            "5.  Come back to Chat — both pills should be green",
        ):
            ctk.CTkLabel(right, text=step, text_color=T.INK_MUTED,
                         font=(T.FONT_FAMILY, 13), justify="left",
                         ).pack(anchor="w", padx=18, pady=1)
        ctk.CTkLabel(right, text="").pack(pady=(0, 12))

    # ---- setup view actions

    def _refresh_addon_dirs(self) -> None:
        for child in self.addon_dirs_frame.winfo_children():
            child.destroy()
        dirs = find_blender_addon_dirs()
        # Preserve any manually-added paths
        existing_manual = [d for d in self._addon_dirs if d.path not in {x.path for x in dirs}]
        self._addon_dirs = dirs + existing_manual

        if not self._addon_dirs:
            ctk.CTkLabel(
                self.addon_dirs_frame,
                text=(
                    "No Blender install detected automatically.\n"
                    "Add a path manually below — typically:\n"
                    r"   %APPDATA%\Blender Foundation\Blender\<X.Y>\scripts\addons"
                ),
                text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13), justify="left",
            ).pack(pady=20, padx=8, anchor="w")
            self._update_addon_actions()
            return

        # auto-pick the latest version if nothing selected
        current = self._addon_selected.get()
        if not current or current not in {str(d.path) for d in self._addon_dirs}:
            self._addon_selected.set(str(self._addon_dirs[0].path))

        for d in self._addon_dirs:
            self._render_addon_row(d)
        self._update_addon_actions()

    def _render_addon_row(self, d: BlenderAddonDir) -> None:
        row = ctk.CTkFrame(self.addon_dirs_frame, fg_color=T.BG_RAISED, corner_radius=T.R_MD)
        row.pack(fill="x", pady=4, padx=4)

        rb = ctk.CTkRadioButton(
            row,
            text="",
            value=str(d.path),
            variable=self._addon_selected,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.EDGE,
            command=self._update_addon_actions,
            width=24,
        )
        rb.pack(side="left", padx=(12, 4), pady=10)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, pady=8)
        title = f"Blender {d.version}"
        if d.is_installed:
            title += f"   ·   ✓ installed v{d.installed_version}"
        ctk.CTkLabel(info, text=title, text_color=T.INK, font=(T.FONT_FAMILY, 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(info, text=str(d.path), text_color=T.INK_DIM,
                     font=(T.FONT_MONO, 12)).pack(anchor="w")

        if d.is_installed:
            tag = ctk.CTkLabel(row, text="installed", text_color=T.OK,
                               font=(T.FONT_FAMILY, 12, "bold"))
        else:
            tag = ctk.CTkLabel(row, text="not installed", text_color=T.INK_DIM,
                               font=(T.FONT_FAMILY, 12))
        tag.pack(side="right", padx=12)

    def _selected_addon_dir(self) -> BlenderAddonDir | None:
        sel = self._addon_selected.get()
        if not sel:
            return None
        for d in self._addon_dirs:
            if str(d.path) == sel:
                return d
        return None

    def _update_addon_actions(self) -> None:
        d = self._selected_addon_dir()
        if d is None:
            self.btn_install.configure(state="disabled")
            self.btn_open_dir.configure(state="disabled")
            self.btn_uninstall.configure(state="disabled")
            self.addon_status_label.configure(text="Select a directory above.", text_color=T.INK_DIM)
            return
        self.btn_install.configure(state="normal", text="⟳  Reinstall / update" if d.is_installed else "⬇  Install addon")
        self.btn_open_dir.configure(state="normal")
        self.btn_uninstall.configure(state="normal" if d.is_installed else "disabled")
        if d.is_installed:
            self.addon_status_label.configure(
                text=f"v{d.installed_version} installed in:\n{d.path}",
                text_color=T.OK,
            )
        else:
            self.addon_status_label.configure(
                text=f"Will install into:\n{d.path}", text_color=T.INK_MUTED,
            )

    def _pick_addon_dir(self) -> None:
        path = filedialog.askdirectory(title="Pick a Blender addons directory")
        if path:
            self.addon_manual_entry.delete(0, "end")
            self.addon_manual_entry.insert(0, path)

    def _add_manual_addon_dir(self) -> None:
        raw = self.addon_manual_entry.get().strip()
        if not raw:
            Toast(self, "Type or browse to a folder first", kind="warn")
            return
        path = Path(raw).expanduser()
        # Try to infer version from path (X.Y component)
        version = "?"
        for part in path.parts:
            if re.match(r"^\d+\.\d+$", part):
                version = part
                break
        from core.addon_installer import read_installed_version, ADDON_FILE_NAME
        installed = read_installed_version(path / ADDON_FILE_NAME)
        existing = next((d for d in self._addon_dirs if d.path == path), None)
        if existing:
            existing.installed_version = installed
        else:
            self._addon_dirs.append(BlenderAddonDir(version=version, path=path, installed_version=installed))
        self._addon_selected.set(str(path))
        # Re-render
        for child in self.addon_dirs_frame.winfo_children():
            child.destroy()
        for d in self._addon_dirs:
            self._render_addon_row(d)
        self._update_addon_actions()

    def _on_install_addon(self) -> None:
        d = self._selected_addon_dir()
        if d is None:
            return
        self.btn_install.configure(state="disabled", text="working…")
        self.addon_status_label.configure(text="installing…", text_color=T.WARN)
        source = self._addon_source.get()
        threading.Thread(target=self._install_addon_worker, args=(d, source), daemon=True).start()

    def _install_addon_worker(self, d: BlenderAddonDir, source: str) -> None:
        try:
            dest = install_addon(d, source=source)
        except Exception as exc:
            self.after(0, lambda: Toast(self, f"Install failed: {exc}", kind="err"))
            self.after(0, lambda: self.addon_status_label.configure(
                text=f"Install failed: {exc}", text_color=T.ERR
            ))
            self.after(0, self._update_addon_actions)
            self.after(0, lambda: self._log(f"addon install failed: {exc}"))
            return
        self.after(0, lambda: Toast(self, f"Addon installed (v{d.installed_version})", kind="ok"))
        self.after(0, lambda: self._log(f"addon installed v{d.installed_version} → {dest}"))
        self.after(0, self._refresh_addon_dirs)

    def _on_open_addon_dir(self) -> None:
        d = self._selected_addon_dir()
        if d is None:
            return
        if not open_addon_dir(d):
            Toast(self, "Could not open file explorer", kind="err")

    def _on_uninstall_addon(self) -> None:
        d = self._selected_addon_dir()
        if d is None or not d.is_installed:
            return
        if uninstall_addon(d):
            Toast(self, "Addon removed", kind="ok")
            self._log(f"addon uninstalled from {d.path}")
            self._refresh_addon_dirs()
        else:
            Toast(self, "Could not remove the addon file", kind="err")

    # =========================================================== models view

    def _build_models_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)
        self._views["models"] = view

        ctk.CTkLabel(view, text="Models", text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )
        ctk.CTkLabel(
            view,
            text="Manage local Ollama models. Q4_K_M is the recommended quantization (best quality / size trade-off).",
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 13),
        ).grid(row=1, column=0, sticky="w", padx=4, pady=(0, 12))

        body = ctk.CTkFrame(view, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Installed list
        installed_card = ctk.CTkFrame(
            body, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE
        )
        installed_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        head1 = ctk.CTkFrame(installed_card, fg_color="transparent")
        head1.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(head1, text="Installed", text_color=T.INK, font=(T.FONT_FAMILY, 15, "bold")).pack(side="left")
        IconButton(head1, text="Refresh", command=self._refresh_models_list, width=84).pack(side="right")

        self.installed_frame = ctk.CTkScrollableFrame(installed_card, fg_color="transparent")
        self.installed_frame.pack(fill="both", expand=True, padx=8, pady=(4, 12))

        # Pull panel
        pull_card = ctk.CTkFrame(
            body, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE
        )
        pull_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(pull_card, text="Pull a model", text_color=T.INK, font=(T.FONT_FAMILY, 15, "bold")).pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        ctk.CTkLabel(
            pull_card,
            text="Recommended (defaults to Q4_K_M):",
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 12),
        ).pack(anchor="w", padx=14)

        self.pull_entry = ctk.CTkEntry(
            pull_card,
            placeholder_text="e.g. qwen2.5-coder:7b",
            fg_color=T.BG_INPUT,
            border_color=T.EDGE,
            text_color=T.INK,
            font=(T.FONT_FAMILY, 14),
        )
        self.pull_entry.pack(fill="x", padx=14, pady=(8, 6))

        for name, desc in RECOMMENDED_MODELS:
            row = ctk.CTkFrame(pull_card, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkButton(
                row,
                text=name,
                width=200,
                height=30,
                fg_color="transparent",
                hover_color=T.BG_RAISED,
                text_color=T.INK,
                border_width=1,
                border_color=T.EDGE,
                anchor="w",
                font=(T.FONT_MONO, 13),
                command=lambda n=name: self._fill_pull(n),
            ).pack(side="left")
            ctk.CTkLabel(row, text=desc, text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)).pack(
                side="left", padx=(8, 0)
            )

        ctk.CTkButton(
            pull_card,
            text="⬇  Pull model",
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_pull_model,
        ).pack(fill="x", padx=14, pady=(10, 6))

        self.pull_progress = ctk.CTkProgressBar(pull_card, progress_color=T.ACCENT, fg_color=T.BG_INPUT)
        self.pull_progress.set(0)
        self.pull_progress.pack(fill="x", padx=14, pady=(2, 4))
        self.pull_status = ctk.CTkLabel(pull_card, text="", text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 12))
        self.pull_status.pack(fill="x", padx=14, pady=(0, 12))

    def _fill_pull(self, name: str) -> None:
        self.pull_entry.delete(0, "end")
        self.pull_entry.insert(0, name)

    def _refresh_models_list(self) -> None:
        for child in self.installed_frame.winfo_children():
            child.destroy()
        if not self.ollama.is_alive():
            ctk.CTkLabel(
                self.installed_frame,
                text="Ollama is offline.\nStart it with `ollama serve`.",
                text_color=T.INK_DIM,
                font=(T.FONT_FAMILY, 14),
                justify="center",
            ).pack(pady=40)
            return
        models = self.ollama.list_models()
        self._refresh_model_combo(models)
        if not models:
            ctk.CTkLabel(
                self.installed_frame,
                text="No models installed yet.\nUse the panel on the right to pull one.",
                text_color=T.INK_DIM,
                font=(T.FONT_FAMILY, 14),
                justify="center",
            ).pack(pady=40)
            return
        for m in models:
            row = ctk.CTkFrame(self.installed_frame, fg_color=T.BG_RAISED, corner_radius=T.R_MD)
            row.pack(fill="x", pady=4, padx=4)
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=12, pady=8)
            ctk.CTkLabel(left, text=m.name, text_color=T.INK, font=(T.FONT_MONO, 14, "bold")).pack(anchor="w")
            tags = " · ".join(filter(None, [m.parameter_size, m.quantization, m.size_human]))
            ctk.CTkLabel(left, text=tags, text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)).pack(anchor="w")
            is_active = m.name == self.settings.ollama_model
            use_btn = ctk.CTkButton(
                row,
                text="Active" if is_active else "Use",
                width=82,
                height=34,
                fg_color=T.ACCENT if is_active else "transparent",
                hover_color=T.ACCENT_HOVER if is_active else T.BG_PANEL,
                text_color="#1a1a1a" if is_active else T.INK_MUTED,
                border_width=0 if is_active else 1,
                border_color=T.EDGE,
                font=(T.FONT_FAMILY, 13),
                command=lambda n=m.name: self._select_model(n),
                state="disabled" if is_active else "normal",
            )
            use_btn.pack(side="right", padx=12)

    def _refresh_model_combo(self, models: list) -> None:
        names = [m.name for m in models] or [self.settings.ollama_model]
        if self.settings.ollama_model not in names:
            names.insert(0, self.settings.ollama_model)
        self.model_combo.configure(values=names)

    def _select_model(self, name: str) -> None:
        self.settings.ollama_model = name
        self._save_settings()
        self.model_combo.set(name)
        self._refresh_models_list()
        Toast(self, f"Model set to {name}", kind="ok")

    def _on_model_changed(self, name: str) -> None:
        self.settings.ollama_model = name
        self._save_settings()
        self._refresh_attach_visibility()

    # ---- vision attach -----------------------------------------------------

    def _refresh_attach_visibility(self) -> None:
        """Show the paperclip only when the active model is vision-capable."""
        if not hasattr(self, "attach_btn"):
            return
        if model_supports_vision(self.settings.ollama_model):
            self.attach_btn.pack_info()  # already packed
            self.attach_btn.configure(state="normal")
        else:
            self.attach_btn.configure(state="disabled")
            self._clear_attached_image()

    def _on_attach_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Attach an image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            self._attached_image_b64 = base64.b64encode(raw).decode("ascii")
            img = PILImage.open(io.BytesIO(raw))
            img.thumbnail((96, 96))
            self._attached_image_thumb = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.attach_thumb_label.configure(image=self._attached_image_thumb, text="")
            self.attach_filename_label.configure(text=Path(path).name)
            self.attach_row.pack(fill="x", before=self._ctrl_row)
        except Exception as exc:
            Toast(self, f"Could not read image: {exc}", kind="err")

    def _clear_attached_image(self) -> None:
        self._attached_image_b64 = None
        self._attached_image_thumb = None
        if hasattr(self, "attach_row"):
            try:
                self.attach_row.pack_forget()
            except Exception:
                pass
            try:
                self.attach_thumb_label.configure(image=None, text="")
                self.attach_filename_label.configure(text="")
            except Exception:
                pass

    def _on_pull_model(self) -> None:
        name = self.pull_entry.get().strip()
        if not name:
            return
        self.pull_progress.set(0)
        self.pull_status.configure(text="starting…")
        threading.Thread(target=self._pull_worker, args=(name,), daemon=True).start()

    def _pull_worker(self, name: str) -> None:
        try:
            for evt in self.ollama.pull_stream(name):
                status = evt.get("status", "")
                total = evt.get("total")
                completed = evt.get("completed")
                if total and completed:
                    pct = completed / total
                    self.after(0, self.pull_progress.set, pct)
                    self.after(0, lambda s=status, p=pct: self.pull_status.configure(
                        text=f"{s} — {p*100:.1f}%"
                    ))
                else:
                    self.after(0, lambda s=status: self.pull_status.configure(text=s))
        except Exception as exc:
            self.after(0, lambda: self.pull_status.configure(text=f"error: {exc}"))
            self.after(0, lambda: Toast(self, f"Pull failed: {exc}", kind="err"))
            return
        self.after(0, self.pull_progress.set, 1.0)
        self.after(0, lambda: self.pull_status.configure(text="✓ pulled"))
        self.after(0, lambda: Toast(self, f"Pulled {name}", kind="ok"))
        self.after(0, self._refresh_models_list)

    # =========================================================== settings view

    def _build_settings_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        self._views["settings"] = view

        ctk.CTkLabel(view, text="Settings", text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 12)
        )

        scroll = ctk.CTkScrollableFrame(view, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        view.grid_rowconfigure(1, weight=1)

        # --- Ollama
        sect = self._settings_section(scroll, "Ollama (local LLM)")
        self.s_ollama_url = self._setting_row(sect, "Endpoint", self.settings.ollama_url,
                                              tooltip="HTTP URL of your Ollama daemon")
        self.s_temp = self._setting_row(sect, "Temperature", str(self.settings.temperature),
                                        tooltip="0.0 = deterministic, 0.2 ≈ default, 0.7+ = creative")
        self.s_keepalive = self._setting_row(sect, "Keep-alive", self.settings.keep_alive,
                                             tooltip="How long Ollama keeps the model loaded after a request, e.g. 5m, 1h, -1 for forever")

        # --- Blender
        sect = self._settings_section(scroll, "Blender (TCP addon)")
        self.s_blender_host = self._setting_row(sect, "Host", self.settings.blender_host,
                                                tooltip="Usually 127.0.0.1 if Blender runs on the same machine")
        self.s_blender_port = self._setting_row(sect, "Port", str(self.settings.blender_port),
                                                tooltip="The addon defaults to 9876")
        IconButton(
            sect, text="Test connection", command=self._test_blender,
            tooltip="Send a ping to the Blender addon", width=190, height=34,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        # --- Behaviour
        sect = self._settings_section(scroll, "Behaviour")
        self.s_persist = ctk.BooleanVar(value=self.settings.persist_history)
        chk = ctk.CTkCheckBox(
            sect, text="Persist conversation history between sessions",
            variable=self.s_persist,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk.pack(anchor="w", padx=14, pady=(4, 4))
        attach_tooltip(chk, "Stored at ~/.ollamatoblender/history.json")

        self.s_route = ctk.BooleanVar(value=self.settings.auto_route_prompt)
        chk2 = ctk.CTkCheckBox(
            sect, text="Auto-route system prompt (query vs build)",
            variable=self.s_route,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk2.pack(anchor="w", padx=14, pady=(0, 4))
        attach_tooltip(chk2, "Read-only inspections get a shorter prompt; creative builds get the full one")

        self.s_updates = ctk.BooleanVar(value=self.settings.check_for_updates)
        chk3 = ctk.CTkCheckBox(
            sect, text="Check GitHub Releases for updates on startup",
            variable=self.s_updates,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk3.pack(anchor="w", padx=14, pady=(0, 4))
        attach_tooltip(chk3, "Notifies if a newer OllamaToBlender release is available")

        # Numeric: max history tokens, max fix attempts
        self.s_max_hist = self._setting_row(sect, "Max history tokens", str(self.settings.max_history_tokens),
                                            tooltip="Older messages are dropped when the conversation exceeds this budget")
        self.s_max_fix = self._setting_row(sect, "Auto-fix attempts", str(self.settings.max_fix_attempts),
                                            tooltip="Maximum number of automatic correction rounds per turn")
        ctk.CTkLabel(sect, text="").pack(pady=(0, 8))

        # --- Appearance
        sect = self._settings_section(scroll, "Appearance")
        appearance_row = ctk.CTkFrame(sect, fg_color="transparent")
        appearance_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(
            appearance_row, text="Theme", text_color=T.INK_MUTED, width=160, anchor="w",
            font=(T.FONT_FAMILY, 13),
        ).pack(side="left")
        self.s_appearance = ctk.CTkSegmentedButton(
            appearance_row,
            values=["dark", "light", "system"],
            command=self._on_appearance_changed,
            fg_color=T.BG_INPUT,
            selected_color=T.ACCENT,
            selected_hover_color=T.ACCENT_HOVER,
            unselected_color=T.BG_RAISED,
            unselected_hover_color=T.EDGE,
            text_color=T.INK,
            font=(T.FONT_FAMILY, 13),
        )
        self.s_appearance.set(self.settings.appearance_mode)
        self.s_appearance.pack(side="left")

        save_row = ctk.CTkFrame(scroll, fg_color="transparent")
        save_row.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(
            save_row,
            text="Save settings",
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_save_settings_clicked,
        ).pack(side="right")

    def _settings_section(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE,
        )
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=title, text_color=T.INK, font=(T.FONT_FAMILY, 15, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        return card

    def _setting_row(self, parent, label: str, value: str, tooltip: str = "") -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        lbl = ctk.CTkLabel(
            row, text=label, text_color=T.INK_MUTED, width=160, anchor="w",
            font=(T.FONT_FAMILY, 13),
        )
        lbl.pack(side="left")
        entry = ctk.CTkEntry(
            row, fg_color=T.BG_INPUT, border_color=T.EDGE, text_color=T.INK,
            font=(T.FONT_FAMILY, 14),
        )
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True)
        if tooltip:
            attach_tooltip(lbl, tooltip)
            attach_tooltip(entry, tooltip)
        return entry

    def _on_appearance_changed(self, value: str) -> None:
        self.settings.appearance_mode = value
        ctk.set_appearance_mode(value)
        self._save_settings()

    def _on_save_settings_clicked(self) -> None:
        try:
            self.settings.ollama_url = self.s_ollama_url.get().strip()
            self.settings.temperature = float(self.s_temp.get().strip() or 0.2)
            self.settings.keep_alive = self.s_keepalive.get().strip() or "5m"
            self.settings.blender_host = self.s_blender_host.get().strip() or "127.0.0.1"
            self.settings.blender_port = int(self.s_blender_port.get().strip() or 9876)
            self.settings.persist_history = bool(self.s_persist.get())
            self.settings.auto_route_prompt = bool(self.s_route.get())
            self.settings.check_for_updates = bool(self.s_updates.get())
            self.settings.max_history_tokens = max(512, int(self.s_max_hist.get().strip() or 8000))
            self.settings.max_fix_attempts = max(0, int(self.s_max_fix.get().strip() or 1))
        except ValueError as exc:
            Toast(self, f"Invalid value: {exc}", kind="err")
            return
        self.ollama = OllamaClient(self.settings.ollama_url)
        self.blender = BlenderClient(self.settings.blender_host, self.settings.blender_port)
        self._save_settings()
        self._refresh_status()
        Toast(self, "Settings saved", kind="ok")

    def _test_blender(self) -> None:
        host = self.s_blender_host.get().strip() or "127.0.0.1"
        try:
            port = int(self.s_blender_port.get().strip() or 9876)
        except ValueError:
            Toast(self, "Port must be an integer", kind="err")
            return
        client = BlenderClient(host, port)
        threading.Thread(target=lambda: self._test_blender_async(client), daemon=True).start()

    def _test_blender_async(self, client: BlenderClient) -> None:
        ok = client.ping()
        self.after(
            0,
            lambda: Toast(
                self,
                "Blender reachable" if ok else "No response from Blender",
                kind="ok" if ok else "err",
            ),
        )

    # =========================================================== logs view

    def _build_logs_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)
        self._views["logs"] = view

        ctk.CTkLabel(view, text="Logs", text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )

        bar = ctk.CTkFrame(view, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            bar,
            text=f"file: {LOG_PATH}",
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        ).pack(side="left")
        IconButton(bar, text="Clear", command=self._clear_logs, width=82, tooltip="Wipe in-memory and on-disk log").pack(side="right")
        IconButton(bar, text="Refresh", command=self._refresh_logs_view, width=92).pack(side="right", padx=(0, 8))

        self.log_box = ctk.CTkTextbox(
            view,
            fg_color=T.BG_PANEL,
            text_color=T.INK_MUTED,
            border_width=1,
            border_color=T.EDGE,
            corner_radius=T.R_MD,
            font=(T.FONT_MONO, 13),
            wrap="none",
        )
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.log_box.configure(state="disabled")

    def _refresh_logs_view(self) -> None:
        if not hasattr(self, "log_box"):
            return
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        if LOG_PATH.exists():
            try:
                self.log_box.insert("1.0", LOG_PATH.read_text(encoding="utf-8"))
            except OSError:
                pass
        else:
            self.log_box.insert("1.0", "(no events yet)")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_logs(self) -> None:
        self._log_lines.clear()
        try:
            LOG_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        self._refresh_logs_view()

    def _log(self, msg: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        self._log_lines.append(line)
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        if self._current_view == "logs":
            self.after(0, self._refresh_logs_view)

    # =========================================================== about view

    def _build_about_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        self._views["about"] = view

        card = ctk.CTkFrame(
            view, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE,
        )
        card.grid(row=0, column=0, sticky="ew", pady=10)

        big = self._ctk_image(ASSETS / "logo.png", (120, 120))
        if big:
            ctk.CTkLabel(card, image=big, text="").pack(pady=(28, 8))
        ctk.CTkLabel(card, text=self.APP_TITLE, text_color=T.INK, font=(T.FONT_FAMILY, 26, "bold")).pack()
        ctk.CTkLabel(
            card, text=f"v{self.APP_VERSION}", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13)
        ).pack(pady=(2, 14))

        body = (
            "Run Blender from a local LLM — no Anthropic, no OpenAI, no API key.\n\n"
            "Pipeline:  natural-language prompt  →  Ollama (Q4_K_M code model)  →  "
            "Python bpy script  →  blender-mcp-addon TCP :9876.\n\n"
            "Recommended model:  qwen2.5-coder:7b  (Q4_K_M, ~4.7 GB)."
        )
        ctk.CTkLabel(
            card, text=body, text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 14),
            wraplength=820, justify="center",
        ).pack(padx=24, pady=(0, 16))

        # Shortcuts
        sc_card = ctk.CTkFrame(view, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE)
        sc_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            sc_card, text="Keyboard shortcuts", text_color=T.INK,
            font=(T.FONT_FAMILY, 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(14, 6))
        for label, accel in [
            ("Send prompt", "Ctrl+Enter"),
            ("Stop streaming", "Esc"),
            ("Clear conversation", "Ctrl+L"),
            ("Focus prompt", "Ctrl+K"),
            ("Open Settings", "Ctrl+,"),
            ("Switch to Chat", "Ctrl+1"),
            ("Switch to Models", "Ctrl+2"),
            ("Switch to Logs", "Ctrl+3"),
        ]:
            r = ctk.CTkFrame(sc_card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=label, text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13)).pack(side="left")
            ctk.CTkLabel(r, text=accel, text_color=T.INK_DIM, font=(T.FONT_MONO, 13)).pack(side="right")
        ctk.CTkLabel(sc_card, text="").pack(pady=(0, 8))

    # =========================================================== status

    def _refresh_status(self) -> None:
        threading.Thread(target=self._refresh_status_async, daemon=True).start()

    def _refresh_status_async(self) -> None:
        ollama_ok = self.ollama.is_alive()
        blender_ok = self.blender.ping()
        self.after(0, self._apply_status, ollama_ok, blender_ok)

    def _refresh_blender_status(self) -> None:
        threading.Thread(
            target=lambda: self.after(0, self._apply_blender_only, self.blender.ping()),
            daemon=True,
        ).start()

    def _apply_status(self, ollama_ok: bool, blender_ok: bool) -> None:
        self.pill_ollama.set_state("ok" if ollama_ok else "err", "Ollama" if ollama_ok else "Ollama offline")
        self.pill_blender.set_state("ok" if blender_ok else "warn", "Blender" if blender_ok else "Blender offline")

    def _apply_blender_only(self, ok: bool) -> None:
        self.pill_blender.set_state("ok" if ok else "warn", "Blender" if ok else "Blender offline")

    def _poll_status_loop(self) -> None:
        self._refresh_status()
        self.after(15000, self._poll_status_loop)

    # =========================================================== shortcuts

    def _wire_shortcuts(self) -> None:
        self.bind_all("<Escape>", lambda _e: self._on_escape())
        self.bind_all("<Control-l>", lambda _e: self._clear_chat())
        self.bind_all("<Control-L>", lambda _e: self._clear_chat())
        self.bind_all("<Control-k>", lambda _e: self._focus_prompt())
        self.bind_all("<Control-K>", lambda _e: self._focus_prompt())
        self.bind_all("<Control-comma>", lambda _e: self.show_view("settings"))
        self.bind_all("<Control-Key-1>", lambda _e: self.show_view("chat"))
        self.bind_all("<Control-Key-2>", lambda _e: self.show_view("setup"))
        self.bind_all("<Control-Key-3>", lambda _e: self.show_view("models"))
        self.bind_all("<Control-Key-4>", lambda _e: self.show_view("logs"))

    def _on_escape(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
            Toast(self, "Streaming stopped", kind="warn", duration_ms=1400)

    def _focus_prompt(self) -> None:
        self.show_view("chat")
        try:
            self._clear_placeholder()
            self.prompt_entry.focus_set()
        except Exception:
            pass

    # =========================================================== persistence

    def _save_settings(self) -> None:
        if hasattr(self, "auto_run_var"):
            self.settings.auto_execute = bool(self.auto_run_var.get())
        if hasattr(self, "auto_fix_var"):
            self.settings.auto_fix_on_error = bool(self.auto_fix_var.get())
        if hasattr(self, "render_var"):
            self.settings.auto_render_preview = bool(self.render_var.get())
        try:
            self.settings.window_geometry = self.winfo_geometry()
        except Exception:
            pass
        self.settings.save()

    def _save_history_async(self) -> None:
        if not self.settings.persist_history:
            return
        snapshot = [t.to_dict() for t in self._chat_turns]
        threading.Thread(target=lambda: save_history(snapshot), daemon=True).start()

    def _restore_history(self) -> None:
        history = load_history()
        if not history:
            return
        if self.empty_state and self.empty_state.winfo_exists():
            self.empty_state.destroy()
        for entry in history:
            prompt = entry.get("prompt", "")
            if not prompt:
                continue
            turn = ChatTurn(
                self.history_frame,
                prompt=prompt,
                model_name=entry.get("model", self.settings.ollama_model),
                on_run=self._on_run_turn,
                on_retry=self._on_retry_turn,
                on_stop=self._on_stop_turn,
            )
            turn.pack(fill="x", pady=(2, 0))
            self._chat_turns.append(turn)
            stats = StreamStats()
            stats.finished_at = stats.started_at  # 0 elapsed
            turn.finish_response(entry.get("response", ""), entry.get("code", ""), stats)
            payload = entry.get("blender_payload") or {}
            status = entry.get("blender_status")
            if status:
                turn.set_blender_result(status, payload)
            self._convo_history.append({"role": "user", "content": prompt})
            if entry.get("response"):
                self._convo_history.append({"role": "assistant", "content": entry["response"]})
        self._scroll_to_bottom()

    def _on_close(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        self._save_settings()
        if self.settings.persist_history:
            try:
                save_history([t.to_dict() for t in self._chat_turns])
            except Exception:
                pass
        self._log("app closing")
        self.destroy()


def main() -> None:
    app = OllamaToBlenderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
