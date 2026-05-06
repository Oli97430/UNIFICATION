"""A single conversational turn rendered as a card with prompt, code, and result."""
from __future__ import annotations

import time
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from core.i18n import t
from core.ollama_client import StreamStats

from . import theme as T
from .widgets import CodeView, IconButton, InlineImage, attach_tooltip


class ChatTurn(ctk.CTkFrame):
    """One user prompt + model output card.

    Lifecycle:
        1. constructor              — user message bubble shown
        2. .start_streaming()       — opens the response panel + spinner
        3. .append_response(token)  — model tokens arrive
        4. .finish_response(...)    — extract & show editable code, enable Run
        5. .set_blender_result(...) — outcome from Blender
    """

    DOT_FRAMES = ["●", "•", "·", "•"]

    def __init__(
        self,
        master,
        prompt: str,
        model_name: str,
        on_run: Callable[["ChatTurn"], None],
        on_retry: Callable[["ChatTurn"], None],
        on_stop: Callable[["ChatTurn"], None] | None = None,
        on_delete: Callable[["ChatTurn"], None] | None = None,
        image_b64: str | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_run = on_run
        self.on_retry = on_retry
        self.on_stop = on_stop
        self.on_delete = on_delete
        self.prompt = prompt
        self.model_name = model_name
        self.image_b64 = image_b64
        self.code: str = ""
        self.full_response: str = ""
        self.blender_status: str = ""
        self.blender_payload: dict = {}
        self._streaming = False
        self._dot_step = 0
        self._dot_after_id: str | None = None
        self._stats: StreamStats | None = None
        self._created_at = time.time()
        self._collapsed = False
        self._on_edit_callback: Callable | None = None

        self._build_user_bubble(prompt)
        self._build_response_card()

    # ------------------------------------------------------------------ build

    def _build_user_bubble(self, text: str) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(row, text="", fg_color="transparent").pack(side="left", expand=True, fill="x")
        bubble = ctk.CTkFrame(
            row,
            fg_color=T.ACCENT_MUTED,
            corner_radius=T.R_LG,
        )
        bubble.pack(side="right", padx=(80, 0))
        if self.image_b64:
            try:
                InlineImage(bubble, b64=self.image_b64, max_size=(280, 200), caption=t("turn.attach.caption")).pack(
                    padx=12, pady=(12, 4), anchor="w",
                )
            except Exception:
                pass
        self._bubble_label = ctk.CTkLabel(
            bubble,
            text=text,
            text_color=T.INK,
            font=(T.FONT_FAMILY, 15),
            justify="left",
            wraplength=1400,
        )
        self._bubble_label.pack(padx=16, pady=12, anchor="w")
        # Edit button on the bubble
        edit_btn = ctk.CTkLabel(
            bubble, text="✎", text_color=T.INK_DIM,
            font=(T.FONT_FAMILY, 14), cursor="hand2",
        )
        edit_btn.pack(anchor="e", padx=(0, 10), pady=(0, 6))
        edit_btn.bind("<Button-1>", lambda _e: self._on_edit_prompt())

    def _build_response_card(self) -> None:
        self.card = ctk.CTkFrame(
            self,
            fg_color=T.BG_PANEL,
            corner_radius=T.R_LG,
            border_width=1,
            border_color=T.EDGE,
        )
        self.card.pack(fill="x", pady=(0, 12))

        # Header strip (clickable to collapse/expand)
        head = ctk.CTkFrame(self.card, fg_color="transparent", cursor="hand2")
        head.pack(fill="x", padx=18, pady=(14, 8))
        head.bind("<Button-1>", lambda _e: self.toggle_collapse())
        self._head_frame = head
        self.spinner = ctk.CTkLabel(head, text="●", text_color=T.ACCENT, font=(T.FONT_FAMILY, 14))
        self.spinner.pack(side="left")
        ctk.CTkLabel(head, text=t("turn.assistant"), text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13, "bold")).pack(side="left")
        ctk.CTkLabel(
            head,
            text=f"  ·  {self.model_name}",
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        ).pack(side="left")

        ctk.CTkLabel(
            head,
            text=f"  ·  {time.strftime('%H:%M', time.localtime(self._created_at))}",
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(head, text=t("turn.thinking"), text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13))
        self.status_label.pack(side="right")
        # Copy response button
        self._copy_btn = ctk.CTkLabel(
            head, text="📋", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 13), cursor="hand2",
        )
        self._copy_btn.pack(side="right", padx=(0, 8))
        self._copy_btn.bind("<Button-1>", lambda _e: self._copy_response())

        # Streaming raw text (replaced by code view once we have a python block)
        self.stream_box = ctk.CTkTextbox(
            self.card,
            height=200,
            fg_color=T.BG_INPUT,
            text_color=T.INK,
            border_width=0,
            font=(T.FONT_FAMILY, 14),
            wrap="word",
            corner_radius=T.R_SM,
        )
        self.stream_box.pack(fill="x", padx=18, pady=(0, 8))
        self.stream_box.configure(state="disabled")

        # Code view (hidden until extraction, editable so the user can tweak before running)
        self.code_view = CodeView(self.card, language="python (bpy)", height=360, editable=True)
        # not packed yet

        # Action bar
        self.actions = ctk.CTkFrame(self.card, fg_color="transparent")
        self.actions.pack(fill="x", padx=18, pady=(0, 10))

        self.run_btn = ctk.CTkButton(
            self.actions,
            text=t("turn.btn.run"),
            command=lambda: self.on_run(self),
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#1a1a1a",
            font=(T.FONT_FAMILY, 14, "bold"),
            corner_radius=T.R_SM,
            height=38,
            state="disabled",
        )
        self.run_btn.pack(side="left")
        attach_tooltip(self.run_btn, t("turn.btn.run.tooltip"))

        self.retry_btn = IconButton(
            self.actions, text=t("turn.btn.regenerate"), command=lambda: self.on_retry(self),
            tooltip=t("turn.btn.regenerate.tooltip"), width=130, height=38,
        )
        self.retry_btn.configure(state="disabled")
        self.retry_btn.pack(side="left", padx=(8, 0))

        self.save_btn = IconButton(
            self.actions, text=t("turn.btn.save_py"), command=self._save_code,
            tooltip=t("turn.btn.save_py.tooltip"), width=92, height=38,
        )
        self.save_btn.configure(state="disabled")
        self.save_btn.pack(side="left", padx=(8, 0))

        self.delete_btn = IconButton(
            self.actions, text=t("turn.btn.delete"), command=self._on_delete_clicked,
            tooltip=t("turn.btn.delete.tooltip"), width=38, height=38,
        )
        self.delete_btn.pack(side="left", padx=(8, 0))

        self.stop_btn = IconButton(
            self.actions, text=t("turn.btn.stop"), command=self._on_stop_clicked,
            tooltip=t("turn.btn.stop.tooltip"), width=92, height=38,
        )
        # Shown only while streaming
        self.stop_btn.configure(state="disabled")

        # Stats footer
        self.stats_label = ctk.CTkLabel(
            self.actions,
            text="",
            text_color=T.INK_DIM,
            font=(T.FONT_MONO, 12),
        )
        self.stats_label.pack(side="right")

        # Result panel (hidden until Blender returns)
        self.result_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.result_status = ctk.CTkLabel(
            self.result_frame, text="", text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13)
        )
        self.result_status.pack(anchor="w", padx=18, pady=(8, 0))
        self.result_box = ctk.CTkTextbox(
            self.result_frame,
            height=200,
            fg_color=T.BG_INPUT,
            text_color=T.INK,
            border_width=1,
            border_color=T.EDGE,
            font=(T.FONT_MONO, 13),
            wrap="word",
            corner_radius=T.R_SM,
        )
        self.result_box.pack(fill="x", padx=18, pady=(4, 12))
        self.result_box.configure(state="disabled")

    # ------------------------------------------------------------------ stream

    def start_streaming(self, stats: StreamStats | None = None) -> None:
        self._streaming = True
        self._stats = stats
        self.status_label.configure(text=t("turn.streaming"), text_color=T.ACCENT)
        self.stop_btn.configure(state="normal")
        self.stop_btn.pack(side="left", padx=(8, 0), before=self.stats_label)
        self._tick_dot()

    def _tick_dot(self) -> None:
        if not self._streaming:
            return
        self._dot_step = (self._dot_step + 1) % len(self.DOT_FRAMES)
        self.spinner.configure(text=self.DOT_FRAMES[self._dot_step])
        self._dot_after_id = self.after(220, self._tick_dot)

    def _stop_dot(self) -> None:
        self._streaming = False
        if self._dot_after_id:
            try:
                self.after_cancel(self._dot_after_id)
            except Exception:
                pass
            self._dot_after_id = None
        self.spinner.configure(text="●")

    def append_response(self, token: str) -> None:
        self.stream_box.configure(state="normal")
        self.stream_box.insert("end", token)
        self.stream_box.see("end")
        self.stream_box.configure(state="disabled")

    def finish_response(self, full_text: str, code: str, stats: StreamStats | None = None) -> None:
        self.full_response = full_text
        self.code = code
        self._stats = stats or self._stats
        self._stop_dot()
        self.stop_btn.pack_forget()

        if stats and stats.aborted:
            self.status_label.configure(text=t("turn.stopped"), text_color=T.WARN)
            self.spinner.configure(text_color=T.WARN)
        else:
            self.status_label.configure(text=t("turn.ready"), text_color=T.OK)
            self.spinner.configure(text_color=T.OK)

        if code and code.strip():
            self.stream_box.pack_forget()
            self.code_view.pack(fill="x", padx=18, pady=(4, 8), before=self.actions)
            self.code_view.set_code(code)
            self.run_btn.configure(state="normal")
            self.save_btn.configure(state="normal")
        else:
            self.stream_box.configure(state="normal")
            self.stream_box.delete("1.0", "end")
            self.stream_box.insert("1.0", full_text or "(empty response)")
            self.stream_box.configure(state="disabled")
        self.retry_btn.configure(state="normal")
        self._render_stats()

    def set_error(self, message: str) -> None:
        self._stop_dot()
        self.stop_btn.pack_forget()
        self.status_label.configure(text=t("turn.error"), text_color=T.ERR)
        self.spinner.configure(text_color=T.ERR)
        self.stream_box.configure(state="normal")
        self.stream_box.delete("1.0", "end")
        self.stream_box.insert("1.0", message)
        self.stream_box.configure(state="disabled")
        self.retry_btn.configure(state="normal")

    def _render_stats(self) -> None:
        if not self._stats:
            return
        s = self._stats
        if s.response_tokens:
            self.stats_label.configure(
                text=f"{s.response_tokens} tok  ·  {s.elapsed_s:0.1f}s  ·  {s.tokens_per_sec:0.1f} tok/s"
            )
        else:
            self.stats_label.configure(text=f"{s.elapsed_s:0.1f}s")

    def _on_stop_clicked(self) -> None:
        if self.on_stop:
            self.on_stop(self)

    def _on_delete_clicked(self) -> None:
        if self.on_delete:
            self.on_delete(self)

    def _on_edit_prompt(self) -> None:
        """Let the user edit their prompt and re-submit (like ChatGPT)."""
        if hasattr(self, "_on_edit_callback") and self._on_edit_callback:
            self._on_edit_callback(self)

    def _copy_response(self) -> None:
        """Copy the full model response text to clipboard."""
        text = self.full_response or ""
        if text:
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
            except Exception:
                pass

    def toggle_collapse(self) -> None:
        """Toggle the response card between collapsed and expanded."""
        if self._collapsed:
            self.card.pack(fill="x", pady=(0, 12))
            self._collapsed = False
        else:
            self.card.pack_forget()
            self._collapsed = True

    def set_prompt_mode(self, mode: str) -> None:
        """Show a badge indicating which system prompt was used."""
        if hasattr(self, "_mode_label"):
            self._mode_label.configure(text=f"  ·  {mode}")
        else:
            self._mode_label = ctk.CTkLabel(
                self._head_frame, text=f"  ·  {mode}",
                text_color=T.INK_DIM, font=(T.FONT_MONO, 11),
            )
            self._mode_label.pack(side="left")

    def _save_code(self) -> None:
        code = self.code_view.get_code()
        if not code.strip():
            return
        path = filedialog.asksaveasfilename(
            title="Save Python script",
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
            initialfile="unification_script.py",
        )
        if not path:
            return
        Path(path).write_text(code, encoding="utf-8")

    # ------------------------------------------------------------------ blender

    def set_blender_running(self) -> None:
        self.run_btn.configure(state="disabled", text=t("turn.btn.run.running"))
        self.result_frame.pack_forget()

    def set_blender_result(self, status: str, payload: dict) -> None:
        self.blender_status = status
        self.blender_payload = payload
        self.run_btn.configure(state="normal", text=t("turn.btn.run"))
        color = {"ok": T.OK, "error": T.ERR, "transport_error": T.ERR}.get(status, T.WARN)
        label = {
            "ok": t("turn.result.ok"),
            "error": t("turn.result.error"),
            "transport_error": t("turn.result.transport_error"),
        }.get(status, status)
        self.result_status.configure(text=label, text_color=color)

        # Pull off the optional viewport-render attachment so it doesn't pollute the textual result.
        result_payload = payload.get("result")
        render_b64: str | None = None
        if isinstance(result_payload, dict) and "_otb_render" in result_payload:
            render_b64 = result_payload.pop("_otb_render")
            if "_otb_user_result" in result_payload and len(result_payload) == 1:
                result_payload = result_payload["_otb_user_result"]

        parts = []
        if payload.get("stdout"):
            parts.append("── stdout ──\n" + payload["stdout"])
        if result_payload is not None:
            parts.append("── result ──\n" + repr(result_payload))
        if payload.get("message"):
            parts.append("── error ──\n" + payload["message"])
        body = "\n\n".join(parts) or t("turn.result.empty")

        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", body)
        self.result_box.configure(state="disabled")

        # Drop any previous render preview before re-packing
        if hasattr(self, "_render_preview") and self._render_preview is not None:
            try:
                self._render_preview.destroy()
            except Exception:
                pass
            self._render_preview = None

        if render_b64:
            try:
                self._render_preview = InlineImage(
                    self.result_frame,
                    b64=render_b64,
                    max_size=(720, 480),
                    caption=t("turn.preview.caption"),
                )
                self._render_preview.pack(fill="x", padx=18, pady=(0, 12))
            except Exception:
                self._render_preview = None
        self.result_frame.pack(fill="x", before=self.actions)

    # ------------------------------------------------------------------ serialise

    def to_dict(self) -> dict:
        return {
            "ts": self._created_at,
            "prompt": self.prompt,
            "model": self.model_name,
            "response": self.full_response,
            "code": self.code_view.get_code() if self.code else "",
            "blender_status": self.blender_status,
            "blender_payload": self.blender_payload,
        }
