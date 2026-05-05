"""TCP client for the blender-mcp-addon (server on port 9876)."""
from __future__ import annotations

import ast
import json
import re
import socket
import textwrap
from dataclasses import dataclass
from typing import Any


def _is_brushes_new_call(call: ast.Call) -> bool:
    f = call.func
    if not (isinstance(f, ast.Attribute) and f.attr == "new"):
        return False
    if not (isinstance(f.value, ast.Attribute) and f.value.attr == "brushes"):
        return False
    if not (isinstance(f.value.value, ast.Attribute) and f.value.value.attr == "data"):
        return False
    root = f.value.value.value
    return isinstance(root, ast.Name) and root.id == "bpy"


_BRUSH_MODES = {
    "SCULPT", "TEXTURE_PAINT", "VERTEX_PAINT", "WEIGHT_PAINT",
    "IMAGE_PAINT", "GPENCIL_PAINT", "GPENCIL_VERTEX",
    "GPENCIL_SCULPT", "GPENCIL_WEIGHT",
}


def _rewrite_brush_call(call: ast.Call) -> ast.expr | None:
    """Normalise a `bpy.data.brushes.new(...)` call. Returns the value to
    assign as the call's `tool=` kwarg (so the caller can append a follow-up
    `<target>.sculpt_tool = X`), or None if no follow-up is needed.

    Two cases:
    1. `tool=<MODE_STRING>` and no `mode=` → rename `tool` to `mode`.
    2. `tool=<X>` and `mode=` already present → drop `tool=` and return X
       so the caller can emit `target.sculpt_tool = X`.
    Also: if `mode=` is missing entirely after step 1, inject mode='SCULPT'.
    """
    tool_kw = next((k for k in call.keywords if k.arg == "tool"), None)
    has_mode = any(k.arg == "mode" for k in call.keywords)
    follow_value: ast.expr | None = None

    if tool_kw is not None:
        is_mode_string = (
            isinstance(tool_kw.value, ast.Constant)
            and isinstance(tool_kw.value.value, str)
            and tool_kw.value.value in _BRUSH_MODES
        )
        if is_mode_string and not has_mode:
            tool_kw.arg = "mode"
            has_mode = True
        else:
            call.keywords = [k for k in call.keywords if k.arg != "tool"]
            follow_value = tool_kw.value

    if not has_mode:
        call.keywords.append(
            ast.keyword(arg="mode", value=ast.Constant(value="SCULPT"))
        )
    return follow_value


class _BrushApiFixer(ast.NodeTransformer):
    """Repair `bpy.data.brushes.new(...)` calls for the Blender 4.x API.

    `BlendDataBrushes.new()` in 4.x only accepts (name, mode); the `tool`
    kwarg was removed. Models still emit the legacy form, sometimes even
    using `tool='SCULPT'` in place of `mode='SCULPT'`. We rewrite both.
    """

    def visit_Assign(self, node: ast.Assign):
        if (
            isinstance(node.value, ast.Call)
            and _is_brushes_new_call(node.value)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            follow_value = _rewrite_brush_call(node.value)
            if follow_value is not None:
                follow = ast.Assign(
                    targets=[
                        ast.Attribute(
                            value=ast.Name(id=node.targets[0].id, ctx=ast.Load()),
                            attr="sculpt_tool",
                            ctx=ast.Store(),
                        )
                    ],
                    value=follow_value,
                )
                return [node, follow]
            return node
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)
        if _is_brushes_new_call(node):
            _rewrite_brush_call(node)
        return node


_BRUSH_TOOL_RE = re.compile(r"brushes\s*\.\s*new\s*\([^)]*\btool\s*=")


def sanitize_code(code: str) -> str:
    """Best-effort rewrite of known-bad Blender 4+ API patterns.

    Currently fixes: `bpy.data.brushes.new(..., tool=X)` → drops the kwarg
    and (when assigned) appends `target.sculpt_tool = X`.

    Only runs the AST transform when a problematic pattern is actually
    detected via regex — this avoids `ast.unparse` stripping comments and
    reformatting user-edited code when no fix is needed.
    """
    if not _BRUSH_TOOL_RE.search(code):
        return code
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    tree = _BrushApiFixer().visit(tree)
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree)
    except Exception:
        return code


@dataclass
class BlenderResult:
    status: str  # "ok" | "error" | "transport_error"
    result: Any = None
    stdout: str = ""
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# A preamble that the client prepends to every script. It finds a VIEW_3D area /
# region and wraps the entire user code in a `temp_override` so calls like
# `bpy.ops.object.select_all`, `mode_set`, `transform.*`, … succeed without
# requiring the model to remember the override boilerplate.
#
# Falls back to a null context when no 3D Viewport is available (headless /
# background mode), so the unwrapped behaviour is preserved in that case.
_V3D_PREAMBLE = """\
import bpy as _otb_bpy
import contextlib as _otb_ctx

def _otb_view3d_override():
    try:
        _scene = _otb_bpy.context.scene
        _vl = _otb_bpy.context.view_layer
        for _w in _otb_bpy.context.window_manager.windows:
            _scr = _w.screen
            for _a in _scr.areas:
                if _a.type == 'VIEW_3D':
                    _rgn = next((_r for _r in _a.regions if _r.type == 'WINDOW'), None)
                    if _rgn is None:
                        continue
                    _kw = {
                        'window': _w, 'screen': _scr, 'area': _a, 'region': _rgn,
                    }
                    if _scene is not None:
                        _kw['scene'] = _scene
                    if _vl is not None:
                        _kw['view_layer'] = _vl
                    return _otb_bpy.context.temp_override(**_kw)
    except Exception:
        pass
    return _otb_ctx.nullcontext()

# Best-effort: drop out of edit-mode so operators with a `mode=='OBJECT'` poll()
# (select_all, delete, transform.*, …) don't trip on stale state.
try:
    _otb_active = _otb_bpy.context.view_layer.objects.active if _otb_bpy.context.view_layer else None
    if _otb_active is not None and getattr(_otb_active, 'mode', 'OBJECT') != 'OBJECT':
        with _otb_view3d_override():
            _otb_bpy.ops.object.mode_set(mode='OBJECT')
except Exception:
    pass

with _otb_view3d_override():
"""


def wrap_with_view3d_override(code: str) -> str:
    """Wrap `code` so it executes inside a VIEW_3D context-override block.

    Variables defined inside a `with` statement live in the enclosing scope,
    so the addon still finds the user's top-level `result = ...`.
    """
    body = textwrap.indent(code.rstrip() + "\n", "    ")
    return _V3D_PREAMBLE + body


# Postamble that renders the active viewport to a PNG and stashes it into
# `result["_otb_render"]` as a base64 string. Used opt-in.
_RENDER_POSTAMBLE = """
# --- OllamaToBlender: viewport preview render -------------------------------
try:
    import base64 as _otb_b64
    import os as _otb_os
    import tempfile as _otb_tmp
    _otb_path = _otb_os.path.join(_otb_tmp.gettempdir(), '_otb_preview.png')
    _otb_scene = _otb_bpy.context.scene
    _otb_prev_path = _otb_scene.render.filepath
    _otb_prev_fmt = _otb_scene.render.image_settings.file_format
    _otb_prev_x = _otb_scene.render.resolution_x
    _otb_prev_y = _otb_scene.render.resolution_y
    _otb_scene.render.filepath = _otb_path
    _otb_scene.render.image_settings.file_format = 'PNG'
    _otb_scene.render.resolution_x = 720
    _otb_scene.render.resolution_y = 480
    with _otb_view3d_override():
        _otb_bpy.ops.render.opengl(write_still=True, view_context=True)
    _otb_scene.render.filepath = _otb_prev_path
    _otb_scene.render.image_settings.file_format = _otb_prev_fmt
    _otb_scene.render.resolution_x = _otb_prev_x
    _otb_scene.render.resolution_y = _otb_prev_y
    with open(_otb_path, 'rb') as _otb_f:
        _otb_png_b64 = _otb_b64.b64encode(_otb_f.read()).decode('ascii')
    if not isinstance(result, dict):
        result = {'_otb_user_result': result}
    result['_otb_render'] = _otb_png_b64
except Exception as _otb_exc:
    pass
"""


def wrap_with_render(code: str) -> str:
    """Wrap user code with VIEW_3D override AND a viewport-render postamble."""
    body = textwrap.indent(code.rstrip() + "\n", "    ")
    return _V3D_PREAMBLE + body + textwrap.indent(_RENDER_POSTAMBLE, "    ")


MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50 MB safety cap


class BlenderClient:
    """Sends Python code to the Blender addon and reads the JSON response."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876, timeout: float = 30.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def ping(self) -> bool:
        """Cheap connectivity check — runs `result = 'pong'` on the addon."""
        r = self.execute("result = 'pong'", timeout=2.0)
        return r.ok and r.result == "pong"

    def execute(
        self,
        code: str,
        timeout: float | None = None,
        *,
        auto_v3d: bool = True,
        with_render: bool = False,
    ) -> BlenderResult:
        code = sanitize_code(code)
        if with_render:
            code = wrap_with_render(code)
        elif auto_v3d:
            code = wrap_with_view3d_override(code)
        payload = json.dumps({"type": "execute", "code": code, "strict_json": False})
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout or self.timeout) as sock:
                sock.settimeout(timeout or self.timeout)
                sock.sendall(payload.encode("utf-8") + b"\x00")
                buf = bytearray()
                while True:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if len(buf) > MAX_RESPONSE_SIZE:
                        raise OSError(f"Response exceeded {MAX_RESPONSE_SIZE // (1024*1024)} MB limit")
                    if b"\x00" in chunk:
                        break
            raw = bytes(buf).rstrip(b"\x00").decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return BlenderResult(
                status=data.get("status", "error"),
                result=data.get("result"),
                stdout=data.get("stdout", ""),
                message=data.get("message", ""),
            )
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            return BlenderResult(status="transport_error", message=f"{type(exc).__name__}: {exc}")
        except json.JSONDecodeError as exc:
            return BlenderResult(status="transport_error", message=f"Invalid JSON from Blender: {exc}")
