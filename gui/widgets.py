"""Reusable widgets: status pills, sidebar buttons, code blocks, toasts, tooltips, images."""
from __future__ import annotations

import base64
import io
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

try:
    from pygments import lex
    from pygments.lexers import PythonLexer

    _HAS_PYGMENTS = True
    _PY_LEXER = PythonLexer()
except Exception:  # pragma: no cover
    _HAS_PYGMENTS = False
    _PY_LEXER = None  # type: ignore[assignment]

from . import theme as T


# Pygments token name → colour. Walks the parent chain when no exact match exists.
_TOKEN_COLOURS = {
    "Token.Keyword": "#ff9450",
    "Token.Keyword.Constant": "#ff9450",
    "Token.Keyword.Declaration": "#ff9450",
    "Token.Keyword.Namespace": "#ff9450",
    "Token.Name.Builtin": "#9b87f5",
    "Token.Name.Builtin.Pseudo": "#9b87f5",
    "Token.Name.Function": "#60a5fa",
    "Token.Name.Class": "#60a5fa",
    "Token.Name.Decorator": "#fbbf24",
    "Token.Literal.String": "#34d399",
    "Token.Literal.String.Single": "#34d399",
    "Token.Literal.String.Double": "#34d399",
    "Token.Literal.String.Doc": "#34d399",
    "Token.Literal.Number": "#fbbf24",
    "Token.Literal.Number.Integer": "#fbbf24",
    "Token.Literal.Number.Float": "#fbbf24",
    "Token.Comment": "#6f7787",
    "Token.Comment.Single": "#6f7787",
    "Token.Operator": "#cbd5e1",
    "Token.Operator.Word": "#ff9450",
    "Token.Punctuation": "#cbd5e1",
}


# ---------------------------------------------------------------- Tooltip


class Tooltip:
    """Lightweight delayed tooltip — attach to any widget."""

    _DELAY_MS = 450

    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _evt=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self._DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        try:
            self._tip.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        frame = tk.Frame(self._tip, bg=T.BG_RAISED, highlightthickness=1, highlightbackground=T.EDGE)
        frame.pack()
        tk.Label(
            frame,
            text=self.text,
            bg=T.BG_RAISED,
            fg=T.INK,
            font=(T.FONT_FAMILY, 12),
            padx=8,
            pady=5,
            justify="left",
        ).pack()
        self._tip.geometry(f"+{x}+{y}")

    def _hide(self, _evt=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def attach_tooltip(widget, text: str) -> Tooltip:
    return Tooltip(widget, text)


# ---------------------------------------------------------------- StatusPill


class StatusPill(ctk.CTkFrame):
    """Compact pill showing a colored dot + label."""

    def __init__(self, master, label: str, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=T.BG_RAISED,
            corner_radius=999,
            border_width=1,
            border_color=T.EDGE,
            **kwargs,
        )
        self.dot = ctk.CTkLabel(self, text="●", text_color=T.INK_DIM, width=14, font=(T.FONT_FAMILY, 14))
        self.dot.pack(side="left", padx=(10, 4), pady=4)
        self.label = ctk.CTkLabel(self, text=label, text_color=T.INK_MUTED, font=(T.FONT_FAMILY, 13))
        self.label.pack(side="left", padx=(0, 12), pady=4)

    def set_state(self, state: str, label: str | None = None) -> None:
        """state ∈ {'ok', 'warn', 'err', 'idle'}"""
        color = {"ok": T.OK, "warn": T.WARN, "err": T.ERR, "idle": T.INK_DIM}.get(state, T.INK_DIM)
        self.dot.configure(text_color=color)
        if label is not None:
            self.label.configure(text=label, text_color=T.INK if state != "idle" else T.INK_MUTED)


# ---------------------------------------------------------------- SidebarButton


class SidebarButton(ctk.CTkButton):
    """Flat sidebar button. The active one gets a raised background."""

    def __init__(self, master, text: str, icon: str = "", command: Callable | None = None, **kwargs) -> None:
        super().__init__(
            master,
            text=f"  {icon}   {text}" if icon else text,
            anchor="w",
            command=command,
            fg_color="transparent",
            hover_color=T.BG_RAISED,
            text_color=T.INK_MUTED,
            corner_radius=T.R_SM,
            height=42,
            font=(T.FONT_FAMILY, 15),
            **kwargs,
        )

    def set_active(self, active: bool) -> None:
        if active:
            self.configure(fg_color=T.BG_RAISED, text_color=T.INK)
        else:
            self.configure(fg_color="transparent", text_color=T.INK_MUTED)


# ---------------------------------------------------------------- CodeView


class CodeView(ctk.CTkFrame):
    """Monospace code display — read-only or editable, with copy + save buttons."""

    def __init__(
        self,
        master,
        language: str = "python",
        height: int = 240,
        editable: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=T.BG_INPUT,
            corner_radius=T.R_MD,
            border_width=1,
            border_color=T.EDGE,
            **kwargs,
        )
        self._editable = editable

        header = ctk.CTkFrame(self, fg_color="transparent", height=34)
        header.pack(fill="x", padx=10, pady=(8, 0))
        self._lang_label = ctk.CTkLabel(
            header, text=language, text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)
        )
        self._lang_label.pack(side="left")

        self._line_count = ctk.CTkLabel(
            header, text="", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12)
        )
        self._line_count.pack(side="left", padx=(10, 0))

        self.copy_btn = ctk.CTkButton(
            header,
            text="Copy",
            width=72,
            height=26,
            fg_color="transparent",
            hover_color=T.BG_RAISED,
            text_color=T.INK_MUTED,
            border_width=1,
            border_color=T.EDGE,
            font=(T.FONT_FAMILY, 12),
            command=self._copy,
        )
        self.copy_btn.pack(side="right")

        self.text = ctk.CTkTextbox(
            self,
            height=height,
            fg_color=T.BG_INPUT,
            text_color=T.INK,
            border_width=0,
            font=(T.FONT_MONO, 14),
            wrap="none",
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # Configure highlight tags up-front (cheap)
        self._highlight_after: str | None = None
        if _HAS_PYGMENTS:
            for token_name, colour in _TOKEN_COLOURS.items():
                try:
                    self.text.tag_config(token_name, foreground=colour)
                except tk.TclError:
                    pass
            if editable:
                self.text.bind("<KeyRelease>", self._schedule_highlight, add="+")

        if not editable:
            self.text.configure(state="disabled")

    def set_code(self, code: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", code)
        self._update_lines()
        self._highlight()
        if not self._editable:
            self.text.configure(state="disabled")

    def append(self, chunk: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", chunk)
        self.text.see("end")
        self._update_lines()
        # Skip highlighting during streaming — it's O(n) per call, causing
        # O(n²) over a full stream. Highlighting is applied once in
        # set_code() / finish_response() or on user edits via _schedule_highlight.
        if not self._editable:
            self.text.configure(state="disabled")

    def get_code(self) -> str:
        return self.text.get("1.0", "end-1c")

    # ---- syntax highlighting --------------------------------------------

    def _schedule_highlight(self, _evt=None) -> None:
        if self._highlight_after:
            try:
                self.after_cancel(self._highlight_after)
            except tk.TclError:
                pass
        self._highlight_after = self.after(120, self._highlight)

    def _highlight(self) -> None:
        if not _HAS_PYGMENTS:
            return
        text = self.text
        try:
            yview = text.yview()
        except tk.TclError:
            yview = None
        for tag in _TOKEN_COLOURS:
            try:
                text.tag_remove(tag, "1.0", "end")
            except tk.TclError:
                pass
        code = text.get("1.0", "end-1c")
        if not code:
            return
        offset = 0
        for tok_type, value in lex(code, _PY_LEXER):
            if not value:
                continue
            length = len(value)
            tag = self._tag_for(tok_type)
            if tag:
                start = text.index(f"1.0 + {offset} chars")
                end = text.index(f"1.0 + {offset + length} chars")
                try:
                    text.tag_add(tag, start, end)
                except tk.TclError:
                    pass
            offset += length
        if yview is not None:
            try:
                text.yview_moveto(yview[0])
            except tk.TclError:
                pass

    @staticmethod
    def _tag_for(tok_type) -> str | None:
        t = tok_type
        while t is not None:
            name = str(t)
            if name in _TOKEN_COLOURS:
                return name
            t = getattr(t, "parent", None)
        return None

    def _update_lines(self) -> None:
        n = int(self.text.index("end-1c").split(".")[0])
        self._line_count.configure(text=f"{n} line{'s' if n != 1 else ''}")

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.get_code())
            self.copy_btn.configure(text="Copied")
            self.after(1100, lambda: self.copy_btn.configure(text="Copy"))
        except tk.TclError:
            pass


# ---------------------------------------------------------------- Toast (stacking)


class _ToastStack:
    """Module-level singleton that stacks toasts above one another."""

    _toasts: list[ctk.CTkFrame] = []

    @classmethod
    def add(cls, toast: ctk.CTkFrame) -> None:
        cls._toasts.append(toast)
        cls._reposition()

    @classmethod
    def remove(cls, toast: ctk.CTkFrame) -> None:
        if toast in cls._toasts:
            cls._toasts.remove(toast)
        cls._reposition()

    @classmethod
    def _reposition(cls) -> None:
        offset = 20
        for t in reversed(cls._toasts):
            try:
                t.place(relx=1.0, rely=1.0, x=-20, y=-offset, anchor="se")
                t.update_idletasks()
                offset += t.winfo_height() + 8
            except tk.TclError:
                pass


class Toast(ctk.CTkFrame):
    """Transient bottom-right notification. Multiple toasts stack."""

    def __init__(self, master, text: str, kind: str = "info", duration_ms: int = 2400) -> None:
        color = {"info": T.ACCENT, "ok": T.OK, "err": T.ERR, "warn": T.WARN}.get(kind, T.ACCENT)
        super().__init__(master, fg_color=T.BG_RAISED, corner_radius=T.R_MD, border_width=1, border_color=color)
        ctk.CTkLabel(self, text="●", text_color=color, font=(T.FONT_FAMILY, 14)).pack(
            side="left", padx=(12, 6), pady=10
        )
        ctk.CTkLabel(self, text=text, text_color=T.INK, font=(T.FONT_FAMILY, 14)).pack(
            side="left", padx=(0, 14), pady=10
        )
        _ToastStack.add(self)
        self.after(duration_ms, self._dismiss)

    def _dismiss(self) -> None:
        _ToastStack.remove(self)
        try:
            self.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------- IconButton


class InlineImage(ctk.CTkFrame):
    """Display a PNG (file path or base64 string), bordered, with a header strip."""

    def __init__(
        self,
        master,
        *,
        image: Image.Image | None = None,
        b64: str | None = None,
        path: Path | None = None,
        max_size: tuple[int, int] = (640, 360),
        caption: str = "",
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=T.BG_INPUT,
            corner_radius=T.R_MD,
            border_width=1,
            border_color=T.EDGE,
            **kwargs,
        )
        if image is None:
            if b64:
                image = Image.open(io.BytesIO(base64.b64decode(b64)))
            elif path:
                image = Image.open(path)
        self._raw = image
        self._caption = caption

        if caption:
            ctk.CTkLabel(
                self, text=caption, text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12),
            ).pack(anchor="w", padx=10, pady=(8, 0))

        if image is not None:
            w, h = image.size
            scale = min(max_size[0] / w, max_size[1] / h, 1.0)
            tw, th = max(1, int(w * scale)), max(1, int(h * scale))
            self._ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(tw, th))
            ctk.CTkLabel(self, image=self._ctk_img, text="").pack(padx=10, pady=10)
        else:
            ctk.CTkLabel(
                self, text="(no image)", text_color=T.INK_DIM, font=(T.FONT_FAMILY, 12),
            ).pack(padx=10, pady=10)


class IconButton(ctk.CTkButton):
    """Compact, square-ish icon button used in toolbars."""

    def __init__(
        self,
        master,
        text: str,
        command: Callable | None = None,
        tooltip: str = "",
        primary: bool = False,
        width: int = 32,
        height: int = 30,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            text=text,
            command=command,
            width=width,
            height=height,
            fg_color=T.ACCENT if primary else "transparent",
            hover_color=T.ACCENT_HOVER if primary else T.BG_RAISED,
            text_color="#1a1a1a" if primary else T.INK_MUTED,
            border_width=0 if primary else 1,
            border_color=T.EDGE,
            corner_radius=T.R_SM,
            font=(T.FONT_FAMILY, 14),
            **kwargs,
        )
        if tooltip:
            attach_tooltip(self, tooltip)
