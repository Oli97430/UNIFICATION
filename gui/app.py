"""Main UNIFICATION window — sidebar + content router."""
from __future__ import annotations

import base64
import io
import json
import queue
import random
import re
import socket
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk
from PIL import Image

from core import (
    ADDON_REMOTE_URL,
    AppAddonDir,
    BlenderAddonDir,
    BlenderClient,
    CREATIVE_APPS,
    LANGUAGE_LABELS,
    OllamaClient,
    PROVIDER_LABELS,
    Settings,
    StreamStats,
    create_provider,
    detect_categories,
    is_query_intent,
    UpdateInfo,
    available_languages,
    check_for_update,
    estimate_history_tokens,
    find_blender_addon_dirs,
    find_freecad_addon_dirs,
    find_gimp_addon_dirs,
    install_addon,
    install_app_addon,
    lint_python,
    load_history,
    model_supports_vision,
    open_addon_dir,
    open_app_addon_dir,
    pick_system_prompt,
    ping_tcp_addon,
    read_bundled_version,
    save_history,
    set_language,
    t,
    trim_history,
    uninstall_addon,
    uninstall_app_addon,
)
from core.ollama_client import RECOMMENDED_MODELS, extract_python_code
from core.settings import LOG_PATH

from . import theme as T
from .chat_turn import ChatTurn
from .widgets import IconButton, SidebarButton, StatusPill, Toast, attach_tooltip


ASSETS = Path(__file__).resolve().parent.parent / "assets"


class UnificationApp(ctk.CTk):
    APP_TITLE = "UNIFICATION"
    APP_VERSION = "2.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()

        # Resolve language BEFORE building any UI — every subsequent t() call depends on it
        set_language(self.settings.language)

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
        self.llm = self._build_provider()
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
        self._scroll_scheduled: bool = False
        self._target_app: str = "blender"  # current execution target: blender|freecad|gimp|…
        self._exec_queue: queue.Queue[tuple[ChatTurn, str, str]] = queue.Queue()
        threading.Thread(target=self._exec_queue_worker, daemon=True).start()

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
            t("header.update.available", version=info.latest),
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
            text=t("app.subtitle"),
            text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 13),
        ).grid(row=0, column=2, sticky="w")

        pills = ctk.CTkFrame(bar, fg_color="transparent")
        pills.grid(row=0, column=3, sticky="e")
        self.pill_ollama = StatusPill(pills, "Ollama")
        self.pill_ollama.pack(side="left", padx=(0, 6))
        attach_tooltip(self.pill_ollama, t("pill.ollama.tooltip"))
        self.pill_ollama.bind("<Button-1>", lambda _e: self._refresh_status())
        self.pill_blender = StatusPill(pills, "Blender")
        self.pill_blender.pack(side="left", padx=(0, 6))
        attach_tooltip(self.pill_blender, t("pill.blender.tooltip"))
        self.pill_blender.bind("<Button-1>", lambda _e: self._refresh_status())

        # Creative-app pills (FreeCAD, GIMP, Inkscape, Photoshop)
        self._app_pills: dict[str, StatusPill] = {}
        for app_key, app_info in CREATIVE_APPS.items():
            pill = StatusPill(pills, app_info["name"])
            pill.pack(side="left", padx=(0, 6))
            attach_tooltip(pill, t(f"pill.{app_key}.tooltip"))
            pill.bind("<Button-1>", lambda _e: self._refresh_status())
            self._app_pills[app_key] = pill

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color=T.BG_PANEL, width=260, corner_radius=T.R_LG)
        side.grid(row=1, column=0, sticky="ns", padx=(16, 12), pady=(8, 16))
        side.grid_propagate(False)

        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(14, 10))

        items = [
            ("chat", t("sidebar.chat"), "💬", "Ctrl+1"),
            ("setup", t("sidebar.setup"), "🧩", "Ctrl+2"),
            ("models", t("sidebar.models"), "📦", "Ctrl+3"),
            ("settings", t("sidebar.settings"), "⚙", "Ctrl+,"),
            ("logs", t("sidebar.logs"), "📜", "Ctrl+4"),
            ("about", t("sidebar.about"), "ⓘ", ""),
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
        ctk.CTkLabel(footer, text=t("sidebar.model_label"), text_color=T.INK_DIM, font=(T.FONT_FAMILY, 11, "bold")).pack(anchor="w")
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
        attach_tooltip(self.model_combo, t("sidebar.model_tooltip"))

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
        self.history_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=(0, 8))

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
            text=t("chat.btn.auto_run"),
            variable=self.auto_run_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        auto_chk.pack(side="left")
        attach_tooltip(auto_chk, t("chat.btn.auto_run.tooltip"))

        self.auto_fix_var = ctk.BooleanVar(value=self.settings.auto_fix_on_error)
        fix_chk = ctk.CTkCheckBox(
            ctrl,
            text=t("chat.btn.auto_fix"),
            variable=self.auto_fix_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        fix_chk.pack(side="left", padx=(12, 0))
        attach_tooltip(fix_chk, t("chat.btn.auto_fix.tooltip"))

        self.render_var = ctk.BooleanVar(value=self.settings.auto_render_preview)
        render_chk = ctk.CTkCheckBox(
            ctrl,
            text=t("chat.btn.preview"),
            variable=self.render_var,
            text_color=T.INK_MUTED,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 13),
            command=self._save_settings,
        )
        render_chk.pack(side="left", padx=(12, 0))
        attach_tooltip(render_chk, t("chat.btn.preview.tooltip"))

        # Token budget indicator
        self._token_label = ctk.CTkLabel(
            ctrl, text="", text_color=T.INK_DIM, font=(T.FONT_MONO, 11),
        )
        self._token_label.pack(side="right", padx=(8, 0))
        attach_tooltip(self._token_label, t("chat.token_budget.tooltip"))

        ctk.CTkLabel(
            ctrl, text=t("chat.hint.send"), text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)
        ).pack(side="left", padx=(16, 0))

        self.export_btn = IconButton(
            ctrl, text=t("chat.btn.export"), command=self._export_conversation,
            tooltip=t("chat.btn.export.tooltip"), width=84,
        )
        self.export_btn.pack(side="right", padx=(8, 0))

        self.clear_btn = IconButton(
            ctrl, text=t("chat.btn.clear"), command=self._clear_chat,
            tooltip=t("chat.btn.clear.tooltip"), width=82,
        )
        self.clear_btn.pack(side="right", padx=(8, 0))

        self.send_btn = ctk.CTkButton(
            ctrl,
            text=t("chat.btn.send"),
            width=130,
            height=36,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_send,
        )
        self.send_btn.pack(side="right")
        attach_tooltip(self.send_btn, t("chat.btn.send.tooltip"))

        self.attach_btn = IconButton(
            ctrl, text="📎", command=self._on_attach_image,
            tooltip=t("chat.btn.attach.tooltip"), width=40,
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

    # Suggestion chips — app key → (display label, number of suggestions, accent colour)
    _SUGGEST_APPS = [
        ("blender",    "Blender",    12, "#E87D0D"),
        ("freecad",    "FreeCAD",    12, "#D94C4C"),
        ("gimp",       "GIMP",       12, "#8C8C00"),
        ("inkscape",   "Inkscape",   12, "#3F72AF"),
        ("photoshop",  "Photoshop",  12, "#31A8FF"),
    ]

    def _build_empty_state(self) -> None:
        self.empty_state = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        self.empty_state.pack(fill="x", pady=(50, 20))

        big = self._ctk_image(ASSETS / "logo.png", (200, 200))
        if big:
            ctk.CTkLabel(self.empty_state, image=big, text="").pack()

        ctk.CTkLabel(
            self.empty_state,
            text="UNIFICATION",
            text_color=T.INK,
            font=(T.FONT_FAMILY, 26, "bold"),
        ).pack(pady=(10, 4))

        ctk.CTkLabel(
            self.empty_state,
            text=t("chat.empty.subtitle"),
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 14),
            justify="center",
        ).pack(pady=(0, 18))

        # Suggestion chips — 4 random examples per creative app, 2-column grid
        for app_key, app_label, total, accent in self._SUGGEST_APPS:
            # App section header
            ctk.CTkLabel(
                self.empty_state, text=f"  {app_label}", text_color=accent,
                font=(T.FONT_FAMILY, 13, "bold"),
            ).pack(anchor="w", padx=40, pady=(10, 0))

            # Pick 4 random suggestions from the 12 available
            indices = list(range(1, total + 1))
            random.shuffle(indices)
            picked = indices[:4]

            grid = ctk.CTkFrame(self.empty_state, fg_color="transparent")
            grid.pack(fill="x", padx=40, pady=(2, 0))
            grid.grid_columnconfigure(0, weight=1)
            grid.grid_columnconfigure(1, weight=1)
            for i, idx in enumerate(picked):
                chip_text = t(f"suggest.{app_key}.{idx}")
                if chip_text.startswith("suggest."):
                    continue  # key missing — skip
                btn = ctk.CTkButton(
                    grid,
                    text=chip_text,
                    fg_color="transparent",
                    hover_color=T.BG_RAISED,
                    text_color=T.INK_MUTED,
                    border_width=1,
                    border_color=T.EDGE,
                    anchor="w",
                    font=(T.FONT_FAMILY, 12),
                    height=36,
                    corner_radius=T.R_SM,
                    command=lambda s=chip_text: self._insert_prompt(s),
                )
                btn.grid(row=i // 2, column=i % 2, padx=3, pady=2, sticky="ew")


    def _insert_prompt(self, text: str) -> None:
        self._clear_placeholder()
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.insert("1.0", text)
        self.prompt_entry.focus_set()

    def _set_placeholder(self) -> None:
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.insert(
            "1.0",
            t("chat.placeholder"),
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
                        is_auto_fix: bool = False, fix_attempt: int = 0,
                        error_context: str | None = None,
                        previous_code: str | None = None) -> None:
        self.send_btn.configure(state="disabled", text="…")

        display_prompt = text if not is_auto_fix else t("turn.fix.attempt", n=fix_attempt)

        turn = ChatTurn(
            self.history_frame,
            prompt=display_prompt,
            model_name=self.settings.ollama_model,
            on_run=self._on_run_turn,
            on_retry=self._on_retry_turn,
            on_stop=self._on_stop_turn,
            on_delete=self._on_delete_turn,
            image_b64=image_b64,
        )
        turn._on_edit_callback = self._on_edit_turn  # type: ignore[attr-defined]
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
            kwargs={"fix_attempt": fix_attempt, "error_context": error_context,
                    "previous_code": previous_code},
            daemon=True,
        ).start()

    def _stream_into_turn(
        self,
        turn: ChatTurn,
        stop_event: threading.Event,
        stats: StreamStats,
        user_msg: str,
        *,
        fix_attempt: int = 0,
        error_context: str | None = None,
        previous_code: str | None = None,
    ) -> None:
        full: list[str] = []
        try:
            # Detect target creative app based on user message + online status
            self._target_app = self._detect_target_app(user_msg)
            target_label = self._target_label(self._target_app)
            # Update run button text to reflect target app
            self.after(0, lambda: turn.run_btn.configure(
                text=f"▶  {t('turn.btn.run.prefix')} {target_label}"))

            # Pick the appropriate system prompt (creator vs query, per app).
            # When auto-route is off, pass empty msg to skip query detection → always creator.
            _prompt_msg = user_msg if self.settings.auto_route_prompt else ""
            sys_prompt = pick_system_prompt(
                _prompt_msg,
                self._target_app,
                provider=self.settings.llm_provider,
                error_context=error_context,
                previous_code=previous_code,
                fix_attempt=fix_attempt,
            )
            prompt_mode = "query" if (self.settings.auto_route_prompt and is_query_intent(user_msg)) else "creator"
            cats = detect_categories(user_msg) if self._target_app == "blender" else []
            self.after(
                0,
                lambda m=prompt_mode, c=cats, fa=fix_attempt: turn.set_prompt_info(m, c, fa),
            )

            # Inject scene context (Blender only — other apps don't have bpy)
            if self.settings.inject_scene_context and self._target_app == "blender":
                try:
                    scene_result = self.blender.execute(
                        "result = [o.name + ' (' + o.type + ')' for o in __import__('bpy').data.objects]",
                        timeout=3.0,
                    )
                    if scene_result.ok and scene_result.result:
                        sys_prompt += f"\n\nCURRENT SCENE OBJECTS: {scene_result.result}"
                except Exception:
                    pass

            # Trim history down to the configured token budget
            kept, dropped = trim_history(
                self._convo_history,
                max_tokens=max(1024, self.settings.max_history_tokens),
                keep_last=6,
            )
            if dropped:
                self._log(f"history trimmed: dropped {len(dropped)} message(s) for budget")
            messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}, *kept]
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.after(0, turn.set_error, f"Setup error: {exc}")
            self.after(0, lambda: self.send_btn.configure(state="normal", text=t("chat.btn.send")))
            self.after(0, self._mark_idle)
            return
        try:
            active_model = self._active_model()
            for token in self.llm.chat_stream(
                model=active_model,
                messages=messages,
                temperature=self.settings.temperature,
                keep_alive=self.settings.keep_alive,
                num_ctx=self.settings.num_ctx,
                stop_event=stop_event,
                stats=stats,
            ):
                full.append(token)
                self.after(0, turn.append_response, token)
                self.after(0, self._scroll_to_bottom_smooth)
        except Exception as exc:
            self.after(0, turn.set_error, f"LLM error: {exc}")
            self.after(0, lambda: self.send_btn.configure(state="normal", text=t("chat.btn.send")))
            self.after(0, lambda: self._log(f"llm error: {exc}"))
            self.after(0, self._mark_idle)
            return

        full_text = "".join(full)
        code = extract_python_code(full_text)
        if not stats.aborted:
            self._convo_history.append({"role": "assistant", "content": full_text})
        self.after(0, turn.finish_response, full_text, code, stats)
        self.after(0, lambda: self.send_btn.configure(state="normal", text=t("chat.btn.send")))
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

    def _update_token_label(self) -> None:
        """Refresh the token budget indicator near the prompt."""
        try:
            used = estimate_history_tokens(self._convo_history)
            budget = self.settings.max_history_tokens
            self._token_label.configure(text=f"{used:,} / {budget:,} tok")
        except Exception:
            pass

    def _mark_idle(self) -> None:
        self._stop_event = None
        self._active_turn = None
        self._save_history_async()
        self.after(0, self._update_token_label)

    def _on_run_turn(self, turn: ChatTurn) -> None:
        code = turn.code_view.get_code() if turn.code else ""
        if not code.strip():
            return
        turn.set_exec_running()
        self._exec_queue.put((turn, code, self._target_app))

    def _exec_queue_worker(self) -> None:
        """Serialize creative-app executions so concurrent Run clicks don't race."""
        while True:
            turn, code, target_app = self._exec_queue.get()
            try:
                if target_app in ("freecad", "gimp", "inkscape", "photoshop"):
                    self._exec_in_app_generic(turn, code, target_app)
                else:
                    self._exec_in_blender(turn, code)
            except Exception:
                pass
            self._exec_queue.task_done()

    def _exec_in_blender(self, turn: ChatTurn, code: str) -> None:
        # Pre-flight lint — catch syntax errors before paying a Blender round-trip
        issues = lint_python(code)
        errors = [i for i in issues if i.level == "error"]
        warns = [i for i in issues if i.level == "warn"]
        if warns:
            self._log(f"lint warnings: {'; '.join(w.format() for w in warns)}")
        if errors:
            msg = "Syntax check failed:\n" + "\n".join(i.format() for i in errors)
            payload = {"result": None, "stdout": "", "message": msg}
            self.after(0, turn.set_exec_result, "error", payload, "Blender")
            self.after(0, lambda: self._log(f"lint failure: {msg}"))
            self.after(0, lambda: self._maybe_auto_fix(turn, msg, "Blender"))
            return
        result = self.blender.execute(
            code,
            timeout=120.0,
            with_render=bool(self.render_var.get()) if hasattr(self, "render_var") else False,
        )
        payload = {"result": result.result, "stdout": result.stdout, "message": result.message}
        self.after(0, turn.set_exec_result, result.status, payload, "Blender")
        self.after(0, self._refresh_blender_status)
        self.after(0, lambda: self._log(f"blender: {result.status}"))
        self.after(0, self._save_history_async)
        if result.status in ("error", "transport_error") and result.message:
            self.after(0, lambda: self._maybe_auto_fix(turn, result.message, "Blender"))

    def _maybe_auto_fix(self, turn: ChatTurn, error_text: str, app_label: str = "Blender") -> None:
        """Spawn an auto-fix turn that asks the model to repair the failing code."""
        if not self.auto_fix_var.get():
            return
        attempts = getattr(turn, "_fix_attempts", 0)
        if attempts >= max(0, self.settings.max_fix_attempts):
            self._log(f"auto-fix budget exhausted ({attempts}/{self.settings.max_fix_attempts})")
            return
        last_code = turn.code_view.get_code() if turn.code else ""
        snippet = error_text.strip()
        if len(snippet) > 1500:
            snippet = snippet[-1500:]
        # User message for the conversation history (short)
        text = (
            f"Fix the error from {app_label}. "
            "Reply with the CORRECTED full script (one ```python``` block, no prose).\n\n"
            f"Error: {snippet[:300]}"
        )
        # Pass full error context + code to the system prompt builder
        self._submit_prompt(
            text,
            is_auto_fix=True,
            fix_attempt=attempts + 1,
            error_context=snippet,
            previous_code=last_code,
        )

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

    def _on_edit_turn(self, turn: ChatTurn) -> None:
        """Edit-and-resubmit: fill the prompt box with the turn's text."""
        self._clear_placeholder()
        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.insert("1.0", turn.prompt)
        self.prompt_entry.focus_set()
        self.show_view("chat")

    def _on_delete_turn(self, turn: ChatTurn) -> None:
        """Remove a single turn from the conversation."""
        if turn in self._chat_turns:
            idx = self._chat_turns.index(turn)
            prompt = turn.prompt
            # Walk backwards: find the user msg, then remove it + the
            # assistant message that immediately follows it (if any).
            to_remove: list[int] = []
            for i in range(len(self._convo_history) - 1, -1, -1):
                entry = self._convo_history[i]
                if entry["role"] == "user" and entry["content"] == prompt:
                    to_remove.append(i)
                    # Also remove the assistant reply right after it
                    if i + 1 < len(self._convo_history) and self._convo_history[i + 1]["role"] == "assistant":
                        to_remove.append(i + 1)
                    break
            for i in sorted(to_remove, reverse=True):
                self._convo_history.pop(i)
            self._chat_turns.pop(idx)
            turn.destroy()
            self._save_history_async()
            if not self._chat_turns:
                self._build_empty_state()

    def _on_stop_turn(self, _turn: ChatTurn) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
            self._log("user stopped streaming")

    def _clear_chat(self) -> None:
        # Guard: confirm if the conversation has substance
        if len(self._chat_turns) > 2:
            dialog = ctk.CTkInputDialog(
                text=t("dialog.clear_confirm"),
                title=t("dialog.clear_title"),
            )
            answer = (dialog.get_input() or "").strip().lower()
            if answer not in ("ok", "oui", "yes", "y"):
                return
        if self._stop_event:
            self._stop_event.set()
        for turn in self._chat_turns:
            try:
                turn.destroy()
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
        # Throttled: ignore calls within 100ms of the last scheduled scroll
        if self._scroll_scheduled:
            return
        self._scroll_scheduled = True
        self.after(100, self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> None:
        self._scroll_scheduled = False
        try:
            _top, bottom = self.history_frame._parent_canvas.yview()
            if bottom > 0.92:
                self.history_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _export_conversation(self) -> None:
        if not self._chat_turns:
            Toast(self, t("toast.nothing_to_export"), kind="warn")
            return
        path = filedialog.asksaveasfilename(
            title=t("dialog.export_title"),
            defaultextension=".json",
            initialfile=f"unification_{datetime.now():%Y%m%d_%H%M%S}.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        save_history([turn.to_dict() for turn in self._chat_turns], Path(path))
        Toast(self, t("toast.exported"), kind="ok")

    # =========================================================== setup view

    _SETUP_APPS = ["Blender", "FreeCAD", "GIMP", "Inkscape", "Photoshop"]

    def _build_setup_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(3, weight=1)
        self._views["setup"] = view

        # ----- header
        ctk.CTkLabel(view, text=t("setup.title"), text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )
        ctk.CTkLabel(
            view,
            text=t("setup.intro"),
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 13),
            justify="left",
            wraplength=1020,
        ).grid(row=1, column=0, sticky="w", padx=4, pady=(0, 8))

        # ----- app selector (segmented button)
        self._setup_app_var = ctk.StringVar(value="Blender")
        seg = ctk.CTkSegmentedButton(
            view,
            values=self._SETUP_APPS,
            variable=self._setup_app_var,
            command=self._on_setup_app_changed,
            font=(T.FONT_FAMILY, 13, "bold"),
            selected_color=T.ACCENT,
            selected_hover_color=T.ACCENT_HOVER,
            unselected_color=T.BG_RAISED,
            unselected_hover_color=T.EDGE,
            text_color=T.INK,
            text_color_disabled=T.INK_DIM,
        )
        seg.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 10))

        # ----- body container — rebuilt when the app segment changes
        self._setup_body = ctk.CTkFrame(view, fg_color="transparent")
        self._setup_body.grid(row=3, column=0, sticky="nsew")

        # Shared state
        self._addon_selected = ctk.StringVar(value="")
        self._addon_dirs: list[BlenderAddonDir] = []
        self._app_addon_dirs: list[AppAddonDir] = []
        self._addon_source = ctk.StringVar(value="remote")

        # Placeholder refs (assigned when body is built)
        self.addon_dirs_frame: ctk.CTkScrollableFrame | None = None
        self.btn_install: ctk.CTkButton | None = None
        self.btn_open_dir: IconButton | None = None
        self.btn_uninstall: IconButton | None = None
        self.addon_status_label: ctk.CTkLabel | None = None
        self.addon_manual_entry: ctk.CTkEntry | None = None

        # Build initial view
        self._build_setup_body()

    def _on_setup_app_changed(self, _value: str = "") -> None:
        self._build_setup_body()

    def _build_setup_body(self) -> None:
        """Rebuild the setup body for the currently selected app."""
        # Clear
        for child in self._setup_body.winfo_children():
            child.destroy()

        app = self._setup_app_var.get()

        if app in ("Inkscape", "Photoshop"):
            self._build_standalone_info(app)
            return

        # ----- installable app (Blender / FreeCAD / GIMP)
        self._setup_body.grid_columnconfigure(0, weight=3)
        self._setup_body.grid_columnconfigure(1, weight=2)
        self._setup_body.grid_rowconfigure(0, weight=1)

        # Left: detected installs
        left = ctk.CTkFrame(
            self._setup_body, fg_color=T.BG_PANEL, corner_radius=T.R_LG,
            border_width=1, border_color=T.EDGE,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        head = ctk.CTkFrame(left, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(head, text=t("setup.detected.title"), text_color=T.INK,
                     font=(T.FONT_FAMILY, 15, "bold")).pack(side="left")
        IconButton(head, text=t("setup.btn.refresh"), command=self._refresh_addon_dirs, width=84).pack(side="right")

        if app == "Blender":
            ctk.CTkLabel(
                left,
                text=t("setup.bundled_version", version=read_bundled_version() or "?"),
                text_color=T.INK_DIM, font=(T.FONT_MONO, 12),
            ).pack(anchor="w", padx=14)

        self.addon_dirs_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.addon_dirs_frame.pack(fill="both", expand=True, padx=8, pady=(8, 12))

        self._addon_selected.set("")

        # Manual path
        manual = ctk.CTkFrame(left, fg_color="transparent")
        manual.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(manual, text=t("setup.custom_path"), text_color=T.INK_MUTED,
                     font=(T.FONT_FAMILY, 12)).pack(anchor="w")
        manual_row = ctk.CTkFrame(manual, fg_color="transparent")
        manual_row.pack(fill="x", pady=(2, 0))
        self.addon_manual_entry = ctk.CTkEntry(
            manual_row,
            placeholder_text=t("setup.btn.browse.tooltip"),
            fg_color=T.BG_INPUT, border_color=T.EDGE, text_color=T.INK,
            font=(T.FONT_MONO, 12),
        )
        self.addon_manual_entry.pack(side="left", fill="x", expand=True)
        IconButton(manual_row, text=t("setup.btn.browse"), command=self._pick_addon_dir, width=82
                   ).pack(side="left", padx=(6, 0))
        IconButton(manual_row, text=t("setup.btn.use"), command=self._add_manual_addon_dir, width=72
                   ).pack(side="left", padx=(6, 0))

        # Right: source + actions
        right = ctk.CTkFrame(
            self._setup_body, fg_color=T.BG_PANEL, corner_radius=T.R_LG,
            border_width=1, border_color=T.EDGE,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Source selector (only Blender has a remote option)
        if app == "Blender":
            ctk.CTkLabel(right, text=t("setup.source.title"), text_color=T.INK,
                         font=(T.FONT_FAMILY, 15, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
            self._addon_source.set("remote")
            for val, label, tip in [
                ("remote", t("setup.source.remote"), f"GET {ADDON_REMOTE_URL}"),
                ("bundled", t("setup.source.bundled"), t("setup.source.bundled.tooltip")),
            ]:
                rb = ctk.CTkRadioButton(
                    right, text=label, value=val, variable=self._addon_source,
                    fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.EDGE,
                    text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13),
                )
                rb.pack(anchor="w", padx=14, pady=2)
                attach_tooltip(rb, tip)
            ctk.CTkLabel(right, text="", height=4).pack()
        else:
            self._addon_source.set("bundled")
            ctk.CTkLabel(right, text="", height=8).pack()

        self.btn_install = ctk.CTkButton(
            right,
            text=t("setup.btn.install"),
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_install_addon, state="disabled",
        )
        self.btn_install.pack(fill="x", padx=14, pady=(2, 6))

        self.btn_open_dir = IconButton(
            right, text=t("setup.btn.open_folder"), command=self._on_open_addon_dir,
            tooltip=t("setup.btn.open_folder.tooltip"), width=210, height=38,
        )
        self.btn_open_dir.configure(state="disabled")
        self.btn_open_dir.pack(fill="x", padx=14, pady=(0, 4))

        self.btn_uninstall = IconButton(
            right, text=t("setup.btn.uninstall"), command=self._on_uninstall_addon,
            tooltip=t("setup.btn.uninstall.tooltip"), width=210, height=38,
        )
        self.btn_uninstall.configure(state="disabled")
        self.btn_uninstall.pack(fill="x", padx=14, pady=(0, 12))

        self.addon_status_label = ctk.CTkLabel(
            right, text=t("setup.status.select"), text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 13), wraplength=380, justify="left",
        )
        self.addon_status_label.pack(anchor="w", padx=14, pady=(0, 12))

        # Next steps
        app_key = app.lower()
        steps_key = f"setup.next_steps.{app_key}"
        ctk.CTkLabel(right, text=t("setup.next_steps.title"), text_color=T.INK,
                     font=(T.FONT_FAMILY, 15, "bold")).pack(anchor="w", padx=14, pady=(2, 4))
        for i in range(1, 6):
            step_text = t(f"{steps_key}.{i}")
            if step_text == f"{steps_key}.{i}":
                break  # key doesn't exist, stop
            ctk.CTkLabel(right, text=step_text, text_color=T.INK_MUTED,
                         font=(T.FONT_FAMILY, 13), justify="left",
                         ).pack(anchor="w", padx=18, pady=1)
        # Optional warning note (FreeCAD, GIMP — macro must be run each session)
        note_key = f"{steps_key}.note"
        note_text = t(note_key)
        if note_text != note_key:
            ctk.CTkLabel(right, text=note_text, text_color=T.ACCENT,
                         font=(T.FONT_FAMILY, 12, "bold"), justify="left",
                         wraplength=350,
                         ).pack(anchor="w", padx=18, pady=(8, 0))
        ctk.CTkLabel(right, text="").pack(pady=(0, 12))

        # Populate left panel
        self._refresh_addon_dirs()

    def _build_standalone_info(self, app: str) -> None:
        """Build info panel for Inkscape / Photoshop (standalone servers)."""
        frame = ctk.CTkFrame(
            self._setup_body, fg_color=T.BG_PANEL, corner_radius=T.R_LG,
            border_width=1, border_color=T.EDGE,
        )
        frame.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(frame, text=t("setup.standalone.title"), text_color=T.INK,
                     font=(T.FONT_FAMILY, 18, "bold")).pack(anchor="w", padx=20, pady=(20, 12))

        key = "setup.standalone." + app.lower()
        info_text = t(key)
        ctk.CTkLabel(
            frame, text=info_text, text_color=T.INK_MUTED,
            font=(T.FONT_MONO, 13), justify="left", wraplength=900,
        ).pack(anchor="w", padx=20, pady=(0, 20))

    # ---- setup view actions

    def _refresh_addon_dirs(self) -> None:
        if self.addon_dirs_frame is None:
            return
        for child in self.addon_dirs_frame.winfo_children():
            child.destroy()

        app = self._setup_app_var.get()
        app_key = app.lower()

        if app == "Blender":
            dirs = find_blender_addon_dirs()
            existing_manual = [d for d in self._addon_dirs if d.path not in {x.path for x in dirs}]
            self._addon_dirs = dirs + existing_manual
            self._app_addon_dirs = []

            if not self._addon_dirs:
                no_install_key = f"setup.no_install.{app_key}"
                ctk.CTkLabel(
                    self.addon_dirs_frame, text=t(no_install_key),
                    text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13), justify="left",
                ).pack(pady=20, padx=8, anchor="w")
                self._update_addon_actions()
                return

            current = self._addon_selected.get()
            if not current or current not in {str(d.path) for d in self._addon_dirs}:
                self._addon_selected.set(str(self._addon_dirs[0].path))
            for d in self._addon_dirs:
                self._render_blender_addon_row(d)
        else:
            # FreeCAD or GIMP
            if app == "FreeCAD":
                dirs_app = find_freecad_addon_dirs()
            else:
                dirs_app = find_gimp_addon_dirs()
            self._app_addon_dirs = dirs_app
            self._addon_dirs = []

            if not self._app_addon_dirs:
                no_install_key = f"setup.no_install.{app_key}"
                ctk.CTkLabel(
                    self.addon_dirs_frame, text=t(no_install_key),
                    text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13), justify="left",
                ).pack(pady=20, padx=8, anchor="w")
                self._update_addon_actions()
                return

            current = self._addon_selected.get()
            if not current or current not in {str(d.path) for d in self._app_addon_dirs}:
                self._addon_selected.set(str(self._app_addon_dirs[0].path))
            for d in self._app_addon_dirs:
                self._render_app_addon_row(d)

        self._update_addon_actions()

    def _render_blender_addon_row(self, d: BlenderAddonDir) -> None:
        row = ctk.CTkFrame(self.addon_dirs_frame, fg_color=T.BG_RAISED, corner_radius=T.R_MD)
        row.pack(fill="x", pady=4, padx=4)

        rb = ctk.CTkRadioButton(
            row, text="", value=str(d.path), variable=self._addon_selected,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.EDGE,
            command=self._update_addon_actions, width=24,
        )
        rb.pack(side="left", padx=(12, 4), pady=10)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, pady=8)
        title = f"Blender {d.version}"
        if d.is_installed:
            title += "   ·   ✓ " + t("setup.installed.tag") + " v" + d.installed_version
        ctk.CTkLabel(info, text=title, text_color=T.INK, font=(T.FONT_FAMILY, 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(info, text=str(d.path), text_color=T.INK_DIM,
                     font=(T.FONT_MONO, 12)).pack(anchor="w")

        tag_text = t("setup.installed.tag") if d.is_installed else t("setup.not_installed.tag")
        tag_color = T.OK if d.is_installed else T.INK_DIM
        ctk.CTkLabel(row, text=tag_text, text_color=tag_color,
                     font=(T.FONT_FAMILY, 12, "bold" if d.is_installed else "normal")
                     ).pack(side="right", padx=12)

    def _render_app_addon_row(self, d: AppAddonDir) -> None:
        row = ctk.CTkFrame(self.addon_dirs_frame, fg_color=T.BG_RAISED, corner_radius=T.R_MD)
        row.pack(fill="x", pady=4, padx=4)

        rb = ctk.CTkRadioButton(
            row, text="", value=str(d.path), variable=self._addon_selected,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.EDGE,
            command=self._update_addon_actions, width=24,
        )
        rb.pack(side="left", padx=(12, 4), pady=10)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, pady=8)
        title = d.label
        if d.is_installed:
            title += "   ·   ✓ " + t("setup.installed.tag") + " v" + d.installed_version
        ctk.CTkLabel(info, text=title, text_color=T.INK, font=(T.FONT_FAMILY, 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(info, text=str(d.path), text_color=T.INK_DIM,
                     font=(T.FONT_MONO, 12)).pack(anchor="w")

        tag_text = t("setup.installed.tag") if d.is_installed else t("setup.not_installed.tag")
        tag_color = T.OK if d.is_installed else T.INK_DIM
        ctk.CTkLabel(row, text=tag_text, text_color=tag_color,
                     font=(T.FONT_FAMILY, 12, "bold" if d.is_installed else "normal")
                     ).pack(side="right", padx=12)

    def _selected_addon_dir(self) -> BlenderAddonDir | None:
        """Return selected Blender addon dir (Blender tab only)."""
        sel = self._addon_selected.get()
        if not sel:
            return None
        for d in self._addon_dirs:
            if str(d.path) == sel:
                return d
        return None

    def _selected_app_addon_dir(self) -> AppAddonDir | None:
        """Return selected app addon dir (FreeCAD / GIMP tabs)."""
        sel = self._addon_selected.get()
        if not sel:
            return None
        for d in self._app_addon_dirs:
            if str(d.path) == sel:
                return d
        return None

    def _update_addon_actions(self) -> None:
        if self.btn_install is None:
            return
        app = self._setup_app_var.get()
        if app == "Blender":
            d = self._selected_addon_dir()
            is_installed = d.is_installed if d else False
            path_str = str(d.path) if d else ""
            version = d.installed_version if d else ""
        else:
            da = self._selected_app_addon_dir()
            is_installed = da.is_installed if da else False
            path_str = str(da.path) if da else ""
            version = da.installed_version if da else ""
            d = da  # type: ignore[assignment]

        if d is None:
            self.btn_install.configure(state="disabled")
            self.btn_open_dir.configure(state="disabled")
            self.btn_uninstall.configure(state="disabled")
            self.addon_status_label.configure(text=t("setup.status.select"), text_color=T.INK_DIM)
            return
        self.btn_install.configure(
            state="normal",
            text=t("setup.btn.reinstall") if is_installed else t("setup.btn.install_only"),
        )
        self.btn_open_dir.configure(state="normal")
        self.btn_uninstall.configure(state="normal" if is_installed else "disabled")
        if is_installed:
            self.addon_status_label.configure(
                text=t("setup.status.installed", version=version, path=path_str),
                text_color=T.OK,
            )
        else:
            self.addon_status_label.configure(
                text=t("setup.status.will_install", path=path_str),
                text_color=T.INK_MUTED,
            )

    def _pick_addon_dir(self) -> None:
        path = filedialog.askdirectory(title=t("setup.btn.browse.tooltip"))
        if path and self.addon_manual_entry:
            self.addon_manual_entry.delete(0, "end")
            self.addon_manual_entry.insert(0, path)

    def _add_manual_addon_dir(self) -> None:
        if not self.addon_manual_entry:
            return
        raw = self.addon_manual_entry.get().strip()
        if not raw:
            Toast(self, t("toast.attach_pick_first"), kind="warn")
            return
        path = Path(raw).expanduser()
        app = self._setup_app_var.get()

        if app == "Blender":
            from core.addon_installer import read_installed_version, ADDON_FILE_NAME
            version = "?"
            for part in path.parts:
                if re.match(r"^\d+\.\d+$", part):
                    version = part
                    break
            installed = read_installed_version(path / ADDON_FILE_NAME)
            existing = next((d for d in self._addon_dirs if d.path == path), None)
            if existing:
                existing.installed_version = installed
            else:
                self._addon_dirs.append(BlenderAddonDir(version=version, path=path, installed_version=installed))
        else:
            from core.addon_installer import (
                read_installed_version, FREECAD_ADDON_FILE, GIMP_ADDON_FILE,
                BUNDLED_FREECAD_PATH, BUNDLED_GIMP_PATH,
            )
            if app == "FreeCAD":
                fname, bundled = FREECAD_ADDON_FILE, BUNDLED_FREECAD_PATH
            else:
                fname, bundled = GIMP_ADDON_FILE, BUNDLED_GIMP_PATH
            installed = read_installed_version(path / fname)
            existing_a = next((d for d in self._app_addon_dirs if d.path == path), None)
            if existing_a:
                existing_a.installed_version = installed
            else:
                self._app_addon_dirs.append(AppAddonDir(
                    app=app.lower(), label=f"{app}  —  {path}",
                    path=path, addon_filename=fname, bundled_path=bundled,
                    installed_version=installed,
                ))

        self._addon_selected.set(str(path))
        self._refresh_addon_dirs()

    def _on_install_addon(self) -> None:
        app = self._setup_app_var.get()
        if app == "Blender":
            d = self._selected_addon_dir()
            if d is None:
                return
            self.btn_install.configure(state="disabled", text=t("setup.status.installing"))
            self.addon_status_label.configure(text=t("setup.status.installing"), text_color=T.WARN)
            source = self._addon_source.get()
            threading.Thread(target=self._install_blender_worker, args=(d, source), daemon=True).start()
        else:
            da = self._selected_app_addon_dir()
            if da is None:
                return
            self.btn_install.configure(state="disabled", text=t("setup.status.installing"))
            self.addon_status_label.configure(text=t("setup.status.installing"), text_color=T.WARN)
            threading.Thread(target=self._install_app_worker, args=(da,), daemon=True).start()

    def _install_blender_worker(self, d: BlenderAddonDir, source: str) -> None:
        try:
            dest = install_addon(d, source=source)
        except Exception as exc:
            self.after(0, lambda: Toast(self, t("toast.addon_install_failed", error=str(exc)), kind="err"))
            self.after(0, lambda: self.addon_status_label.configure(
                text=t("setup.status.failed", error=str(exc)), text_color=T.ERR
            ))
            self.after(0, self._update_addon_actions)
            self.after(0, lambda: self._log(f"Blender addon install failed: {exc}"))
            return
        self.after(0, lambda: Toast(self, t("toast.addon_installed", version=d.installed_version), kind="ok"))
        self.after(0, lambda: self._log(f"Blender addon installed v{d.installed_version} → {dest}"))
        self.after(0, self._refresh_addon_dirs)

    def _install_app_worker(self, d: AppAddonDir) -> None:
        try:
            dest = install_app_addon(d)
        except Exception as exc:
            self.after(0, lambda: Toast(self, t("toast.addon_install_failed", error=str(exc)), kind="err"))
            self.after(0, lambda: self.addon_status_label.configure(
                text=t("setup.status.failed", error=str(exc)), text_color=T.ERR
            ))
            self.after(0, self._update_addon_actions)
            self.after(0, lambda: self._log(f"{d.app} addon install failed: {exc}"))
            return
        self.after(0, lambda: Toast(self, t("toast.addon_installed", version=d.installed_version), kind="ok"))
        self.after(0, lambda: self._log(f"{d.app} addon installed v{d.installed_version} → {dest}"))
        self.after(0, self._refresh_addon_dirs)

    def _on_open_addon_dir(self) -> None:
        app = self._setup_app_var.get()
        if app == "Blender":
            d = self._selected_addon_dir()
            if d is None:
                return
            if not open_addon_dir(d):
                Toast(self, t("toast.cant_open_explorer"), kind="err")
        else:
            da = self._selected_app_addon_dir()
            if da is None:
                return
            if not open_app_addon_dir(da):
                Toast(self, t("toast.cant_open_explorer"), kind="err")

    def _on_uninstall_addon(self) -> None:
        app = self._setup_app_var.get()
        if app == "Blender":
            d = self._selected_addon_dir()
            if d is None or not d.is_installed:
                return
            if uninstall_addon(d):
                Toast(self, t("toast.addon_removed"), kind="ok")
                self._log(f"Blender addon uninstalled from {d.path}")
                self._refresh_addon_dirs()
            else:
                Toast(self, t("toast.addon_remove_failed"), kind="err")
        else:
            da = self._selected_app_addon_dir()
            if da is None or not da.is_installed:
                return
            if uninstall_app_addon(da):
                Toast(self, t("toast.addon_removed"), kind="ok")
                self._log(f"{da.app} addon uninstalled from {da.path}")
                self._refresh_addon_dirs()
            else:
                Toast(self, t("toast.addon_remove_failed"), kind="err")

    # =========================================================== models view

    def _build_models_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)
        self._views["models"] = view

        ctk.CTkLabel(view, text=t("models.title"), text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )
        ctk.CTkLabel(
            view,
            text=t("models.subtitle"),
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
        ctk.CTkLabel(head1, text=t("models.installed.title"), text_color=T.INK, font=(T.FONT_FAMILY, 15, "bold")).pack(side="left")
        IconButton(head1, text=t("models.btn.refresh"), command=self._refresh_models_list, width=84).pack(side="right")

        self.installed_frame = ctk.CTkScrollableFrame(installed_card, fg_color="transparent")
        self.installed_frame.pack(fill="both", expand=True, padx=8, pady=(4, 12))

        # Pull panel
        pull_card = ctk.CTkFrame(
            body, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE
        )
        pull_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(pull_card, text=t("models.pull.title"), text_color=T.INK, font=(T.FONT_FAMILY, 15, "bold")).pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        ctk.CTkLabel(
            pull_card,
            text=t("models.pull.recommended"),
            text_color=T.INK_MUTED,
            font=(T.FONT_FAMILY, 12),
        ).pack(anchor="w", padx=14)

        self.pull_entry = ctk.CTkEntry(
            pull_card,
            placeholder_text=t("models.pull.placeholder"),
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
            text=t("models.pull.btn"),
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            command=self._on_pull_model,
        ).pack(fill="x", padx=14, pady=(10, 6))

        pull_bottom = ctk.CTkFrame(pull_card, fg_color="transparent")
        pull_bottom.pack(fill="x", padx=14, pady=(2, 4))
        self.pull_progress = ctk.CTkProgressBar(pull_bottom, progress_color=T.ACCENT, fg_color=T.BG_INPUT)
        self.pull_progress.set(0)
        self.pull_progress.pack(side="left", fill="x", expand=True)
        self.pull_cancel_btn = IconButton(
            pull_bottom, text=t("turn.btn.stop"), command=self._cancel_pull,
            tooltip=t("models.pull.cancel_tooltip"), width=72, height=28,
        )
        self.pull_cancel_btn.pack(side="right", padx=(6, 0))
        self.pull_cancel_btn.configure(state="disabled")
        self._pull_stop = threading.Event()
        self.pull_status = ctk.CTkLabel(pull_card, text="", text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 12))
        self.pull_status.pack(fill="x", padx=14, pady=(0, 12))

    def _fill_pull(self, name: str) -> None:
        self.pull_entry.delete(0, "end")
        self.pull_entry.insert(0, name)

    def _refresh_models_list(self) -> None:
        for child in self.installed_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.installed_frame, text="⟳", text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 14),
        ).pack(pady=40)
        threading.Thread(target=self._refresh_models_list_async, daemon=True).start()

    def _refresh_models_list_async(self) -> None:
        alive = self.ollama.is_alive()
        models = self.ollama.list_models() if alive else []
        self.after(0, self._refresh_models_list_apply, alive, models)

    def _refresh_models_list_apply(self, alive: bool, models) -> None:
        for child in self.installed_frame.winfo_children():
            child.destroy()
        if not alive:
            ctk.CTkLabel(
                self.installed_frame,
                text=t("models.ollama_offline"),
                text_color=T.INK_DIM,
                font=(T.FONT_FAMILY, 14),
                justify="center",
            ).pack(pady=40)
            return
        self._refresh_model_combo(models)
        if not models:
            ctk.CTkLabel(
                self.installed_frame,
                text=t("models.installed.empty"),
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
                text=t("models.btn.active") if is_active else t("models.btn.use"),
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
        Toast(self, t("toast.model_set", name=name), kind="ok")

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
            title=t("dialog.attach_title"),
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
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((96, 96))
            self._attached_image_thumb = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.attach_thumb_label.configure(image=self._attached_image_thumb, text="")
            self.attach_filename_label.configure(text=Path(path).name)
            self.attach_row.pack(fill="x", before=self._ctrl_row)
        except Exception as exc:
            Toast(self, t("toast.image_error", error=str(exc)), kind="err")

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
        self._pull_stop.clear()
        self.pull_cancel_btn.configure(state="normal")
        self.pull_status.configure(text=t("models.pull.starting"))
        threading.Thread(target=self._pull_worker, args=(name,), daemon=True).start()

    def _cancel_pull(self) -> None:
        self._pull_stop.set()
        self.pull_cancel_btn.configure(state="disabled")

    def _pull_worker(self, name: str) -> None:
        try:
            for evt in self.ollama.pull_stream(name):
                if self._pull_stop.is_set():
                    self.after(0, lambda: self.pull_status.configure(text=t("models.pull.cancelled")))
                    self.after(0, lambda: self.pull_cancel_btn.configure(state="disabled"))
                    return
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
            self.after(0, lambda: self.pull_status.configure(text=t("models.pull.error", error=str(exc))))
            self.after(0, lambda: Toast(self, t("toast.pull_failed", error=str(exc)), kind="err"))
            self.after(0, lambda: self.pull_cancel_btn.configure(state="disabled"))
            return
        self.after(0, self.pull_progress.set, 1.0)
        self.after(0, lambda: self.pull_status.configure(text=t("models.pull.done")))
        self.after(0, lambda: Toast(self, t("toast.pulled", name=name), kind="ok"))
        self.after(0, lambda: self.pull_cancel_btn.configure(state="disabled"))
        self.after(0, self._refresh_models_list)

    # =========================================================== settings view

    def _build_settings_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        self._views["settings"] = view

        ctk.CTkLabel(view, text=t("settings.title"), text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 12)
        )

        scroll = ctk.CTkScrollableFrame(view, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        view.grid_rowconfigure(1, weight=1)

        # --- LLM Provider
        sect = self._settings_section(scroll, t("settings.section.provider"))
        provider_keys = list(PROVIDER_LABELS.keys())
        provider_labels = list(PROVIDER_LABELS.values())
        current_idx = provider_keys.index(self.settings.llm_provider) if self.settings.llm_provider in provider_keys else 0
        self.s_provider = ctk.CTkOptionMenu(
            sect, values=provider_labels,
            fg_color=T.BG_RAISED, button_color=T.ACCENT,
            button_hover_color=T.ACCENT_HOVER, text_color=T.INK,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.INK,
            dropdown_hover_color=T.ACCENT,
            font=(T.FONT_FAMILY, 13), width=250,
            command=self._on_provider_changed,
        )
        self.s_provider.set(provider_labels[current_idx])
        self.s_provider.pack(anchor="w", padx=14, pady=(4, 8))

        # API key + model fields for cloud providers
        self._provider_frame = ctk.CTkFrame(sect, fg_color="transparent")
        self._provider_frame.pack(fill="x", padx=0, pady=(0, 4))

        self.s_claude_key = self._setting_row(self._provider_frame, t("settings.provider.api_key", provider="Claude"), self.settings.claude_api_key, show="*")
        self.s_claude_model = self._setting_row(self._provider_frame, t("settings.provider.model", provider="Claude"), self.settings.claude_model)
        self.s_openai_key = self._setting_row(self._provider_frame, t("settings.provider.api_key", provider="OpenAI"), self.settings.openai_api_key, show="*")
        self.s_openai_model = self._setting_row(self._provider_frame, t("settings.provider.model", provider="OpenAI"), self.settings.openai_model)
        self.s_gemini_key = self._setting_row(self._provider_frame, t("settings.provider.api_key", provider="Gemini"), self.settings.gemini_api_key, show="*")
        self.s_gemini_model = self._setting_row(self._provider_frame, t("settings.provider.model", provider="Gemini"), self.settings.gemini_model)
        self._toggle_provider_fields()

        # --- Ollama
        sect = self._settings_section(scroll, t("settings.section.ollama"))
        self.s_ollama_url = self._setting_row(sect, t("settings.endpoint"), self.settings.ollama_url,
                                              tooltip=t("settings.endpoint.tooltip"))
        self.s_temp = self._setting_row(sect, t("settings.temperature"), str(self.settings.temperature),
                                        tooltip=t("settings.temperature.tooltip"))
        self.s_keepalive = self._setting_row(sect, t("settings.keepalive"), self.settings.keep_alive,
                                             tooltip=t("settings.keepalive.tooltip"))

        # --- Blender
        sect = self._settings_section(scroll, t("settings.section.blender"))
        self.s_blender_host = self._setting_row(sect, t("settings.host"), self.settings.blender_host,
                                                tooltip=t("settings.host.tooltip"))
        self.s_blender_port = self._setting_row(sect, t("settings.port"), str(self.settings.blender_port),
                                                tooltip=t("settings.port.tooltip"))
        IconButton(
            sect, text=t("settings.btn.test_connection"), command=self._test_blender,
            tooltip=t("settings.btn.test_connection.tooltip"), width=190, height=34,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        # --- Behaviour
        sect = self._settings_section(scroll, t("settings.section.behaviour"))
        self.s_persist = ctk.BooleanVar(value=self.settings.persist_history)
        chk = ctk.CTkCheckBox(
            sect, text=t("settings.persist"),
            variable=self.s_persist,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk.pack(anchor="w", padx=14, pady=(4, 4))
        attach_tooltip(chk, t("settings.persist.tooltip"))

        self.s_route = ctk.BooleanVar(value=self.settings.auto_route_prompt)
        chk2 = ctk.CTkCheckBox(
            sect, text=t("settings.route"),
            variable=self.s_route,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk2.pack(anchor="w", padx=14, pady=(0, 4))
        attach_tooltip(chk2, t("settings.route.tooltip"))

        self.s_updates = ctk.BooleanVar(value=self.settings.check_for_updates)
        chk3 = ctk.CTkCheckBox(
            sect, text=t("settings.updates"),
            variable=self.s_updates,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk3.pack(anchor="w", padx=14, pady=(0, 4))
        attach_tooltip(chk3, t("settings.updates.tooltip"))

        self.s_scene_ctx = ctk.BooleanVar(value=self.settings.inject_scene_context)
        chk4 = ctk.CTkCheckBox(
            sect, text=t("settings.scene_ctx"),
            variable=self.s_scene_ctx,
            text_color=T.INK_MUTED, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.EDGE, font=(T.FONT_FAMILY, 13),
        )
        chk4.pack(anchor="w", padx=14, pady=(0, 4))
        attach_tooltip(chk4, t("settings.scene_ctx.tooltip"))

        # Numeric: max history tokens, max fix attempts, num_ctx
        self.s_max_hist = self._setting_row(sect, t("settings.max_history"), str(self.settings.max_history_tokens),
                                            tooltip=t("settings.max_history.tooltip"))
        self.s_max_fix = self._setting_row(sect, t("settings.max_fix"), str(self.settings.max_fix_attempts),
                                            tooltip=t("settings.max_fix.tooltip"))
        self.s_num_ctx = self._setting_row(sect, t("settings.num_ctx"), str(self.settings.num_ctx),
                                            tooltip=t("settings.num_ctx.tooltip"))
        ctk.CTkLabel(sect, text="").pack(pady=(0, 8))

        # --- Appearance
        sect = self._settings_section(scroll, t("settings.section.appearance"))
        appearance_row = ctk.CTkFrame(sect, fg_color="transparent")
        appearance_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(
            appearance_row, text=t("settings.theme"), text_color=T.INK_MUTED, width=160, anchor="w",
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

        # Language selector
        lang_row = ctk.CTkFrame(sect, fg_color="transparent")
        lang_row.pack(fill="x", padx=14, pady=(4, 12))
        lang_label_w = ctk.CTkLabel(
            lang_row, text=t("settings.language"), text_color=T.INK_MUTED, width=160, anchor="w",
            font=(T.FONT_FAMILY, 13),
        )
        lang_label_w.pack(side="left")
        attach_tooltip(lang_label_w, t("settings.language.tooltip"))
        lang_codes = ["auto", *available_languages()]
        lang_display = ["Auto", *[LANGUAGE_LABELS.get(c, c) for c in available_languages()]]
        self._lang_display_to_code = dict(zip(lang_display, lang_codes))
        self.s_language = ctk.CTkSegmentedButton(
            lang_row,
            values=lang_display,
            command=self._on_language_changed,
            fg_color=T.BG_INPUT,
            selected_color=T.ACCENT,
            selected_hover_color=T.ACCENT_HOVER,
            unselected_color=T.BG_RAISED,
            unselected_hover_color=T.EDGE,
            text_color=T.INK,
            font=(T.FONT_FAMILY, 13),
        )
        code_to_display = {v: k for k, v in self._lang_display_to_code.items()}
        self.s_language.set(code_to_display.get(self.settings.language, "Auto"))
        self.s_language.pack(side="left")
        # CTkSegmentedButton does not support .bind(), so only the label gets a tooltip.

        save_row = ctk.CTkFrame(scroll, fg_color="transparent")
        save_row.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(
            save_row,
            text=t("settings.btn.save"),
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

    def _setting_row(self, parent, label: str, value: str, tooltip: str = "", show: str = "") -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        lbl = ctk.CTkLabel(
            row, text=label, text_color=T.INK_MUTED, width=160, anchor="w",
            font=(T.FONT_FAMILY, 13),
        )
        lbl.pack(side="left")
        kwargs: dict = dict(
            fg_color=T.BG_INPUT, border_color=T.EDGE, text_color=T.INK,
            font=(T.FONT_FAMILY, 14),
        )
        if show:
            kwargs["show"] = show
        entry = ctk.CTkEntry(row, **kwargs)
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

    def _on_language_changed(self, display: str) -> None:
        code = self._lang_display_to_code.get(display, "auto")
        self.settings.language = code
        applied = set_language(code)
        self._save_settings()
        Toast(self, t("toast.language_restart"), kind="warn", duration_ms=4000)
        self._log(f"language switched to {applied}")

    def _on_provider_changed(self, value: str) -> None:
        """Update settings when provider dropdown changes."""
        keys = list(PROVIDER_LABELS.keys())
        labels = list(PROVIDER_LABELS.values())
        idx = labels.index(value) if value in labels else 0
        self.settings.llm_provider = keys[idx]
        self._toggle_provider_fields()

    def _toggle_provider_fields(self) -> None:
        """Show/hide API key + model fields based on selected provider."""
        p = self.settings.llm_provider
        # Each row is packed inside _provider_frame — show/hide by pack/forget
        claude_widgets = [self.s_claude_key, self.s_claude_model]
        openai_widgets = [self.s_openai_key, self.s_openai_model]
        gemini_widgets = [self.s_gemini_key, self.s_gemini_model]
        for w in claude_widgets + openai_widgets + gemini_widgets:
            w.master.pack_forget()
        if p == "claude":
            for w in claude_widgets:
                w.master.pack(fill="x", padx=14, pady=4)
        elif p == "openai":
            for w in openai_widgets:
                w.master.pack(fill="x", padx=14, pady=4)
        elif p == "gemini":
            for w in gemini_widgets:
                w.master.pack(fill="x", padx=14, pady=4)

    def _on_save_settings_clicked(self) -> None:
        try:
            # Provider settings
            provider_keys = list(PROVIDER_LABELS.keys())
            provider_labels = list(PROVIDER_LABELS.values())
            sel = self.s_provider.get()
            idx = provider_labels.index(sel) if sel in provider_labels else 0
            self.settings.llm_provider = provider_keys[idx]
            self.settings.claude_api_key = self.s_claude_key.get().strip()
            self.settings.claude_model = self.s_claude_model.get().strip() or "claude-sonnet-4-20250514"
            self.settings.openai_api_key = self.s_openai_key.get().strip()
            self.settings.openai_model = self.s_openai_model.get().strip() or "gpt-4o"
            self.settings.gemini_api_key = self.s_gemini_key.get().strip()
            self.settings.gemini_model = self.s_gemini_model.get().strip() or "gemini-2.5-flash"

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
            self.settings.num_ctx = max(2048, int(self.s_num_ctx.get().strip() or 8192))
            self.settings.inject_scene_context = bool(self.s_scene_ctx.get())
        except ValueError as exc:
            Toast(self, t("toast.invalid_value", error=str(exc)), kind="err")
            return
        # Sync inline chat toggles into settings
        if hasattr(self, "auto_run_var"):
            self.settings.auto_execute = bool(self.auto_run_var.get())
        if hasattr(self, "auto_fix_var"):
            self.settings.auto_fix_on_error = bool(self.auto_fix_var.get())
        if hasattr(self, "render_var"):
            self.settings.auto_render_preview = bool(self.render_var.get())
        self.ollama = OllamaClient(self.settings.ollama_url)
        self.llm = self._build_provider()
        self.blender = BlenderClient(self.settings.blender_host, self.settings.blender_port)
        self._save_settings()
        self._refresh_status()
        Toast(self, t("toast.settings_saved"), kind="ok")

    def _test_blender(self) -> None:
        host = self.s_blender_host.get().strip() or "127.0.0.1"
        try:
            port = int(self.s_blender_port.get().strip() or 9876)
        except ValueError:
            Toast(self, t("toast.invalid_port"), kind="err")
            return
        client = BlenderClient(host, port)
        threading.Thread(target=lambda: self._test_blender_async(client), daemon=True).start()

    def _test_blender_async(self, client: BlenderClient) -> None:
        ok = client.ping()
        self.after(
            0,
            lambda: Toast(
                self,
                t("toast.blender_reachable") if ok else t("toast.blender_unreachable"),
                kind="ok" if ok else "err",
            ),
        )

    # =========================================================== logs view

    def _build_logs_view(self) -> None:
        view = ctk.CTkFrame(self.content, fg_color=T.BG_BASE)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)
        self._views["logs"] = view

        ctk.CTkLabel(view, text=t("logs.title"), text_color=T.INK, font=(T.FONT_FAMILY, 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 6)
        )

        bar = ctk.CTkFrame(view, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkLabel(
            bar,
            text=t("logs.file", path=str(LOG_PATH)),
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        ).pack(side="left")
        IconButton(bar, text=t("logs.btn.clear"), command=self._clear_logs, width=82, tooltip=t("logs.btn.clear.tooltip")).pack(side="right")
        IconButton(bar, text=t("logs.btn.refresh"), command=self._refresh_logs_view, width=92).pack(side="right", padx=(0, 8))

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
            self.log_box.insert("1.0", t("logs.empty"))
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

        big = self._ctk_image(ASSETS / "logo.png", (200, 200))
        if big:
            ctk.CTkLabel(card, image=big, text="").pack(pady=(28, 8))
        ctk.CTkLabel(card, text=self.APP_TITLE, text_color=T.INK, font=(T.FONT_FAMILY, 26, "bold")).pack()
        ctk.CTkLabel(
            card, text=f"v{self.APP_VERSION}", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13)
        ).pack(pady=(2, 14))

        ctk.CTkLabel(
            card, text=t("about.body"), text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 14),
            wraplength=820, justify="center",
        ).pack(padx=24, pady=(0, 16))

        # Shortcuts
        sc_card = ctk.CTkFrame(view, fg_color=T.BG_PANEL, corner_radius=T.R_LG, border_width=1, border_color=T.EDGE)
        sc_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            sc_card, text=t("about.shortcuts.title"), text_color=T.INK,
            font=(T.FONT_FAMILY, 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(14, 6))
        for label, accel in [
            (t("shortcut.send"), "Ctrl+Enter"),
            (t("shortcut.stop"), "Esc"),
            (t("shortcut.clear"), "Ctrl+L"),
            (t("shortcut.focus"), "Ctrl+K"),
            (t("shortcut.settings"), "Ctrl+,"),
            (t("shortcut.chat"), "Ctrl+1"),
            (t("shortcut.setup"), "Ctrl+2"),
            (t("shortcut.models"), "Ctrl+3"),
            (t("shortcut.logs"), "Ctrl+4"),
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
        # Run ALL checks in parallel
        results: dict[str, bool] = {}
        def _check_ollama():
            try:
                results["ollama"] = self.ollama.is_alive()
            except Exception:
                results["ollama"] = False
        def _check_blender():
            try:
                results["blender"] = self.blender.ping()
            except Exception:
                results["blender"] = False
        def _check_app(key: str, port: int):
            try:
                results[key] = ping_tcp_addon(self.settings.blender_host, port)
            except Exception:
                results[key] = False

        threads = [
            threading.Thread(target=_check_ollama, daemon=True),
            threading.Thread(target=_check_blender, daemon=True),
        ]
        for app_key, app_info in CREATIVE_APPS.items():
            threads.append(threading.Thread(target=_check_app, args=(app_key, app_info["port"]), daemon=True))
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)
        self.after(0, self._apply_status_all, results)

    def _refresh_blender_status(self) -> None:
        def _ping():
            try:
                ok = self.blender.ping()
            except Exception:
                ok = False
            self.after(0, self._apply_blender_only, ok)
        threading.Thread(target=_ping, daemon=True).start()

    def _apply_status_all(self, results: dict[str, bool]) -> None:
        ollama_ok = results.get("ollama", False)
        blender_ok = results.get("blender", False)
        self.pill_ollama.set_state("ok" if ollama_ok else "err", t("pill.ollama") if ollama_ok else t("pill.ollama.offline"))
        self.pill_blender.set_state("ok" if blender_ok else "warn", t("pill.blender") if blender_ok else t("pill.blender.offline"))
        for app_key, pill in self._app_pills.items():
            ok = results.get(app_key, False)
            pill.set_state(
                "ok" if ok else "warn",
                t(f"pill.{app_key}") if ok else t(f"pill.{app_key}.offline"),
            )

    # Legacy alias kept for _refresh_blender_status callback
    def _apply_blender_only(self, ok: bool) -> None:
        self.pill_blender.set_state("ok" if ok else "warn", t("pill.blender") if ok else t("pill.blender.offline"))

    # ---- target-app detection & generic TCP execution ----

    def _detect_target_app(self, user_msg: str = "") -> str:
        """Determine which creative app to target based on online status + keywords.

        Priority:
        1. Explicit keyword in user message
        2. First online creative app (Blender checked first)
        3. Default to blender
        """
        lower = user_msg.lower()
        # Explicit keyword match — check all 5 apps
        if "freecad" in lower or "free cad" in lower:
            return "freecad"
        if "inkscape" in lower:
            return "inkscape"
        if "photoshop" in lower:
            return "photoshop"
        if "gimp" in lower:
            return "gimp"
        if "blender" in lower:
            return "blender"
        # Check which apps are online (pill state)
        if self.pill_blender.state == "ok":
            return "blender"
        for app_key in ("freecad", "gimp", "inkscape", "photoshop"):
            pill = self._app_pills.get(app_key)
            if pill and pill.state == "ok":
                return app_key
        return "blender"  # fallback

    # ── LLM provider helpers ────────────────────────────────────────

    def _build_provider(self):
        """Create the active LLM provider from current settings."""
        p = self.settings.llm_provider
        if p == "claude":
            return create_provider("claude", api_key=self.settings.claude_api_key)
        if p == "openai":
            return create_provider("openai", api_key=self.settings.openai_api_key)
        if p == "gemini":
            return create_provider("gemini", api_key=self.settings.gemini_api_key)
        return create_provider("ollama", base_url=self.settings.ollama_url)

    def _active_model(self) -> str:
        """Return the model name for the active provider."""
        p = self.settings.llm_provider
        if p == "claude":
            return self.settings.claude_model
        if p == "openai":
            return self.settings.openai_model
        if p == "gemini":
            return self.settings.gemini_model
        return self.settings.ollama_model

    def _target_port(self, app: str) -> int:
        """Return the TCP port for the given app key."""
        if app == "blender":
            return self.settings.blender_port
        info = CREATIVE_APPS.get(app)
        return info["port"] if info else 9876

    def _target_label(self, app: str) -> str:
        """Human-readable label for the target app."""
        labels = {"blender": "Blender", "freecad": "FreeCAD", "gimp": "GIMP",
                  "inkscape": "Inkscape", "photoshop": "Photoshop"}
        return labels.get(app, app.capitalize())

    def _exec_in_app_generic(self, turn: ChatTurn, code: str, app: str) -> None:
        """Execute code in a non-Blender creative app via raw TCP."""
        app_label = self._target_label(app)
        port = self._target_port(app)
        host = self.settings.blender_host  # same host for all apps
        request = json.dumps({"type": "execute", "code": code})

        backoff = 1.0
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with socket.create_connection((host, port), timeout=120.0) as sock:
                    sock.settimeout(120.0)
                    sock.sendall(request.encode("utf-8") + b"\x00")
                    buf = bytearray()
                    _MAX_RESP = 50 * 1024 * 1024  # 50 MB cap (same as BlenderClient)
                    while True:
                        chunk = sock.recv(8192)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        if len(buf) > _MAX_RESP:
                            raise RuntimeError(f"Response too large (>{_MAX_RESP // (1024*1024)} MB)")
                        if b"\x00" in chunk:
                            break
                raw = bytes(buf).rstrip(b"\x00").decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                result_payload = {
                    "result": data.get("result"),
                    "stdout": data.get("stdout", ""),
                    "message": data.get("message", ""),
                }
                status = data.get("status", "error")
                self.after(0, turn.set_exec_result, status, result_payload, app_label)
                self.after(0, self._refresh_status)
                self.after(0, lambda: self._log(f"{app}: {status}"))
                self.after(0, self._save_history_async)
                if status in ("error", "transport_error") and data.get("message"):
                    err_msg = data.get("message", "")
                    self.after(0, lambda e=err_msg: self._maybe_auto_fix(turn, e, app_label))
                return
            except ConnectionRefusedError as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 15.0)
                    continue
            except Exception as exc:
                result_payload = {"result": None, "stdout": "", "message": f"{type(exc).__name__}: {exc}"}
                self.after(0, turn.set_exec_result, "transport_error", result_payload, app_label)
                self.after(0, lambda: self._log(f"{app}: transport_error"))
                return

        result_payload = {"result": None, "stdout": "",
                          "message": f"ConnectionRefusedError after 3 attempts: {last_exc}"}
        self.after(0, turn.set_exec_result, "transport_error", result_payload, app_label)
        self.after(0, lambda: self._log(f"{app}: connection refused"))

    def _poll_status_loop(self) -> None:
        # Skip polling when window is minimized or iconified
        try:
            if self.state() != "iconic":
                self._refresh_status()
        except Exception:
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
            Toast(self, t("toast.stopped"), kind="warn", duration_ms=1400)

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
        snapshot = [turn.to_dict() for turn in self._chat_turns]
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
                on_delete=self._on_delete_turn,
            )
            turn._on_edit_callback = self._on_edit_turn
            turn.pack(fill="x", pady=(2, 0))
            self._chat_turns.append(turn)
            stats = StreamStats()
            stats.finished_at = stats.started_at  # 0 elapsed
            turn.finish_response(entry.get("response", ""), entry.get("code", ""), stats)
            payload = entry.get("blender_payload") or {}
            status = entry.get("blender_status")
            if status:
                turn.set_exec_result(status, payload)
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
                save_history([turn.to_dict() for turn in self._chat_turns])
            except Exception:
                pass
        self._log("app closing")
        self.destroy()


def main() -> None:
    app = UnificationApp()
    app.mainloop()


if __name__ == "__main__":
    main()
