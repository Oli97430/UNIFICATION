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
                            attr="sculpt_brush_type",
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


# Principled BSDF socket renames (Blender 4.x).  Maps legacy → new name.
_BSDF_SOCKET_RENAMES: dict[str, str] = {
    "Subsurface":          "Subsurface Weight",
    "Subsurface Color":    "Subsurface Radius",
    "Specular":            "Specular IOR Level",
    "Transmission":        "Transmission Weight",
    "Clearcoat":           "Coat Weight",
    "Clearcoat Roughness": "Coat Roughness",
    "Clearcoat Normal":    "Coat Normal",
    "Sheen":               "Sheen Weight",
    "Emission":            "Emission Color",
}

# Match  .inputs["LegacyName"]  with optional whitespace
_BSDF_INPUT_RE = re.compile(
    r'\.inputs\s*\[\s*(["\'])'
    r'(' + '|'.join(re.escape(k) for k in _BSDF_SOCKET_RENAMES) + r')'
    r'\1\s*\]'
)

_SCULPT_TOOL_RE = re.compile(r"\.sculpt_tool\b")
_BRUSH_TOOL_RE = re.compile(r"brushes\s*\.\s*new\s*\([^)]*\btool\s*=")
_EXPORT_OBJ_RE = re.compile(r"bpy\.ops\.export_scene\.obj\s*\(")
_IMPORT_OBJ_RE = re.compile(r"bpy\.ops\.import_scene\.obj\s*\(")
_LIGHT_ADD_HEMI_RE = re.compile(r"light_add\s*\([^)]*type\s*=\s*['\"]HEMI['\"]")
_BSDF_BY_NAME_RE = re.compile(r"""nodes\s*\[\s*["']Principled BSDF["']\s*\]""")

# Common shader/GN node names that models look up by label instead of type.
# Maps display name → Blender internal node type for type-based lookup.
_NODE_NAME_TYPE_MAP: dict[str, str] = {
    "Geometry":           "NEW_GEOMETRY",
    "Material Output":    "OUTPUT_MATERIAL",
    "World Output":       "OUTPUT_WORLD",
    "Group Input":        "GROUP_INPUT",
    "Group Output":       "GROUP_OUTPUT",
    "Mix Shader":         "MIX_SHADER",
    "Texture Coordinate": "TEX_COORD",
    "Image Texture":      "TEX_IMAGE",
    "ColorRamp":          "VALTORGB",
    "Mapping":            "MAPPING",
}
_NODE_BY_NAME_RE = re.compile(
    r"""nodes\s*\[\s*["']("""
    + "|".join(re.escape(k) for k in _NODE_NAME_TYPE_MAP)
    + r""")["']\s*\]"""
)
_MATHUTILS_RADIANS_RE = re.compile(r"\bmathutils\.(radians|degrees)\b")
# Match brush.size = 50.0  (float literal for an int property)
_BRUSH_SIZE_FLOAT_RE = re.compile(r"(\.size\s*=\s*)(\d+)\.0\b")
# Match bpy.ops.mesh.displace(
_MESH_DISPLACE_RE = re.compile(r"bpy\.ops\.mesh\.displace\s*\(")
# Match  X.brush = ...  where X is a sculpt/paint tool settings variable.
# Covers: sculpt.brush = ..., ts.brush = ..., tool_settings.sculpt.brush = ...
# In Blender 5.x, .brush is read-only on ALL paint/sculpt tool_settings.
_SCULPT_BRUSH_ASSIGN_RE = re.compile(
    r"^(\s*)"                                 # leading indent
    r"(\w+(?:\.\w+)*)\.brush\s*=\s*(.+)$",   # any_var.brush = value
    re.MULTILINE,
)
# Match subdivision_set(levels=…) — should be level= (singular) in Blender 5.x
_SUBDIV_LEVELS_RE = re.compile(r"(subdivision_set\s*\([^)]*)\blevels\b")


def _fix_subdivision_levels(code: str) -> str:
    """Fix `subdivision_set(levels=N)` → `subdivision_set(level=N)`.

    Blender's operator uses `level` (singular); models often hallucinate `levels`.
    """
    return _SUBDIV_LEVELS_RE.sub(r"\1level", code)


def _auto_inject_import_bpy(code: str) -> str:
    """Prepend `import bpy` if code references `bpy` but never imports it."""
    if re.search(r"^\s*import\s+bpy\b", code, re.MULTILINE):
        return code
    if "bpy." in code or "bpy " in code:
        return "import bpy\n" + code
    return code


def _fix_export_obj(code: str) -> str:
    """Replace removed `bpy.ops.export_scene.obj(...)` with `bpy.ops.wm.obj_export(...)`."""
    return _EXPORT_OBJ_RE.sub("bpy.ops.wm.obj_export(", code)


def _fix_import_obj(code: str) -> str:
    """Replace removed `bpy.ops.import_scene.obj(...)` with `bpy.ops.wm.obj_import(...)`."""
    return _IMPORT_OBJ_RE.sub("bpy.ops.wm.obj_import(", code)


def _fix_light_hemi(code: str) -> str:
    """Replace `type='HEMI'` with `type='AREA'` in light_add calls."""
    return _LIGHT_ADD_HEMI_RE.sub(
        lambda m: m.group(0).replace("HEMI", "AREA"), code
    )


def _fix_bsdf_by_name(code: str) -> str:
    """Replace `nodes["Principled BSDF"]` with the type-based lookup."""
    return _BSDF_BY_NAME_RE.sub(
        "next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)", code
    )


def _fix_node_by_name(code: str) -> str:
    """Replace `nodes["Geometry"]` (and other common names) with type-based lookup.

    Models hallucinate node names that are locale-dependent or simply wrong.
    A type-based lookup is always reliable.
    """
    def _repl(m: re.Match) -> str:
        name = m.group(1)
        ntype = _NODE_NAME_TYPE_MAP[name]
        return f"next((n for n in nodes if n.type == '{ntype}'), None)"
    return _NODE_BY_NAME_RE.sub(_repl, code)


def _fix_mathutils_radians(code: str) -> str:
    """Replace `mathutils.radians(…)` / `mathutils.degrees(…)` with `math.*`.

    `mathutils` does not have `radians`/`degrees` — they live in the stdlib `math` module.
    Models confuse the two because both are imported together in typical Blender scripts.
    Also auto-injects `import math` if missing.
    """
    if not _MATHUTILS_RADIANS_RE.search(code):
        return code
    code = _MATHUTILS_RADIANS_RE.sub(lambda m: f"math.{m.group(1)}", code)
    # Ensure `import math` is present
    if not re.search(r"^\s*import\s+math\b", code, re.MULTILINE):
        code = "import math\n" + code
    return code


def _fix_sculpt_tool_attr(code: str) -> str:
    """Replace `.sculpt_tool` with `.sculpt_brush_type` (renamed in Blender 5.x)."""
    return _SCULPT_TOOL_RE.sub(".sculpt_brush_type", code)


def _fix_sculpt_brush_assign(code: str) -> str:
    """Comment out `X.brush = Y` assignments (read-only in Blender 5.x).

    `.brush` is read-only on sculpt / paint tool_settings objects.
    Replaces with a comment explaining the issue.
    """
    if not _SCULPT_BRUSH_ASSIGN_RE.search(code):
        return code

    def _repl(m: re.Match) -> str:
        indent = m.group(1)
        lhs = m.group(2)
        rhs = m.group(3).strip()
        return (
            f"{indent}# .brush is read-only in Blender 5.x — assignment removed\n"
            f"{indent}# original: {lhs}.brush = {rhs}"
        )

    return _SCULPT_BRUSH_ASSIGN_RE.sub(_repl, code)


def _fix_brush_size_float(code: str) -> str:
    """Replace `.size = 50.0` with `.size = 50` (Brush.size expects int)."""
    return _BRUSH_SIZE_FLOAT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", code)


def _fix_bsdf_socket_renames(code: str) -> str:
    r"""Replace legacy BSDF input names with Blender 4.x names.

    Rewrites e.g. `.inputs["Subsurface Color"]` → `.inputs["Subsurface Radius"]`.
    Only touches the known-renamed sockets; stable names pass through untouched.
    """
    def _repl(m: re.Match) -> str:
        quote = m.group(1)
        legacy = m.group(2)
        new = _BSDF_SOCKET_RENAMES.get(legacy, legacy)
        return f'.inputs[{quote}{new}{quote}]'
    return _BSDF_INPUT_RE.sub(_repl, code)


def sanitize_code(code: str) -> str:
    """Best-effort rewrite of known-bad Blender 4+ API patterns.

    Applies, in order:
    1. Auto-inject `import bpy` if missing.
    2. Regex-based rewrites (export_scene.obj → wm.obj_export,
       import_scene.obj → wm.obj_import, HEMI → AREA,
       nodes["Principled BSDF"] → type-based lookup,
       nodes["Geometry"/…] → type-based lookup (10 common node names),
       BSDF socket renames for 4.x,
       mathutils.radians/degrees → math.radians/degrees).
    3. AST-based brush fixer (only when `brushes.new(tool=…)` detected).
    """
    code = _auto_inject_import_bpy(code)
    code = _fix_export_obj(code)
    code = _fix_import_obj(code)
    code = _fix_light_hemi(code)
    code = _fix_bsdf_by_name(code)
    code = _fix_node_by_name(code)
    code = _fix_bsdf_socket_renames(code)
    code = _fix_sculpt_tool_attr(code)
    code = _fix_sculpt_brush_assign(code)
    code = _fix_brush_size_float(code)
    code = _fix_subdivision_levels(code)
    code = _fix_mathutils_radians(code)

    # AST pass — only when needed (ast.unparse strips comments)
    if _BRUSH_TOOL_RE.search(code):
        try:
            tree = ast.parse(code)
            tree = _BrushApiFixer().visit(tree)
            ast.fix_missing_locations(tree)
            code = ast.unparse(tree)
        except Exception:
            pass
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
# --- UNIFICATION: viewport preview render -----------------------------------
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
        retries: int = 3,
    ) -> BlenderResult:
        code = sanitize_code(code)
        if with_render:
            code = wrap_with_render(code)
        elif auto_v3d:
            code = wrap_with_view3d_override(code)
        payload = json.dumps({"type": "execute", "code": code, "strict_json": False})

        backoff = 1.0
        last_exc: Exception | None = None
        for attempt in range(max(1, retries)):
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
            except ConnectionRefusedError as exc:
                last_exc = exc
                if attempt < retries - 1:
                    import time
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 15.0)
                    continue
            except (socket.timeout, OSError) as exc:
                return BlenderResult(status="transport_error", message=f"{type(exc).__name__}: {exc}")
            except json.JSONDecodeError as exc:
                return BlenderResult(status="transport_error", message=f"Invalid JSON from Blender: {exc}")
        return BlenderResult(status="transport_error", message=f"ConnectionRefusedError after {retries} attempts: {last_exc}")
