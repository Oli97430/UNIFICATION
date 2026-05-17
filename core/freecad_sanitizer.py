"""AST/regex sanitizer for FreeCAD Python code.

Mirrors the Blender sanitizer (blender_client.sanitize_code) but targets
common FreeCAD / OpenCASCADE pitfalls such as:

- Missing imports (FreeCAD, Part, Draft, Sketcher, PartDesign, Mesh)
- Missing ``doc = App.ActiveDocument or App.newDocument(...)``
- Missing ``doc.recompute()``
- Unguarded ``makeFillet`` / ``makeChamfer`` on potentially empty edge lists
- Float arguments where int is expected (``Length = 10.0`` is fine,
  but ``addObject("Part::Box", 10)`` is wrong)
"""
from __future__ import annotations

import re

# ------------------------------------------------------------------ #
# 1. Auto-inject imports                                              #
# ------------------------------------------------------------------ #

_IMPORT_MAP: dict[str, str] = {
    "FreeCAD": "import FreeCAD as App",
    "App":     "import FreeCAD as App",
    "Part":    "import Part",
    "Draft":   "import Draft",
    "Sketcher": "import Sketcher",
    "PartDesign": "import PartDesign",
    "Mesh":    "import Mesh",
    "BOPTools": "import BOPTools",
    "Arch":    "import Arch",
}


def _auto_inject_imports(code: str) -> str:
    """Prepend missing ``import X`` lines when ``X.`` appears in code."""
    injections: list[str] = []
    for symbol, import_line in _IMPORT_MAP.items():
        # Only inject if the symbol is actually used (``App.`` or ``Part.``)
        if re.search(rf"\b{symbol}\b", code) and not re.search(
            rf"^\s*import\s+{symbol.split()[0]}\b", code, re.MULTILINE
        ):
            # Avoid double-injection for App/FreeCAD
            if symbol in ("FreeCAD", "App"):
                if re.search(r"^\s*import\s+FreeCAD\b", code, re.MULTILINE):
                    continue
            if import_line not in injections:
                injections.append(import_line)
    if injections:
        code = "\n".join(injections) + "\n" + code
    return code


# ------------------------------------------------------------------ #
# 2. Auto-inject document initialisation                              #
# ------------------------------------------------------------------ #

_DOC_ASSIGN_RE = re.compile(r"^\s*doc\s*=", re.MULTILINE)
_DOC_USAGE_RE  = re.compile(r"\bdoc\b")


def _auto_inject_doc(code: str) -> str:
    """Ensure ``doc = App.ActiveDocument or App.newDocument(...)`` exists."""
    if not _DOC_USAGE_RE.search(code):
        return code
    if _DOC_ASSIGN_RE.search(code):
        return code
    # The doc init line needs App, so make sure it's imported
    if not re.search(r"^\s*import\s+FreeCAD\b", code, re.MULTILINE):
        code = "import FreeCAD as App\n" + code
    # Insert after the last import line
    lines = code.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*(import |from )", line):
            insert_idx = i + 1
    lines.insert(insert_idx, 'doc = App.ActiveDocument or App.newDocument("Unnamed")')
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# 3. Auto-inject doc.recompute()                                     #
# ------------------------------------------------------------------ #

_RECOMPUTE_RE = re.compile(r"\brecompute\s*\(")


def _auto_inject_recompute(code: str) -> str:
    """Append ``doc.recompute()`` if code touches ``doc.`` but never recomputes."""
    if not re.search(r"\bdoc\.", code):
        return code
    if _RECOMPUTE_RE.search(code):
        return code
    return code.rstrip() + "\ndoc.recompute()\n"


# ------------------------------------------------------------------ #
# 4. Guard makeFillet / makeChamfer on empty edge lists               #
# ------------------------------------------------------------------ #

_FILLET_RE = re.compile(
    r"^(\s*)"                                    # indent
    r"(\w+)\s*=\s*(\w+)\.makeFillet\("           # var = shape.makeFillet(
    r"([^,]+),\s*"                               # radius,
    r"(\w+)"                                     # edges_variable
    r"\)",                                       # )
    re.MULTILINE,
)
_CHAMFER_RE = re.compile(
    r"^(\s*)"
    r"(\w+)\s*=\s*(\w+)\.makeChamfer\("
    r"([^,]+),\s*"
    r"(\w+)"
    r"\)",
    re.MULTILINE,
)


def _guard_fillet_chamfer(code: str) -> str:
    """Wrap ``x = y.makeFillet(r, edges)`` in ``if edges:`` guard."""
    def _repl_fillet(m: re.Match) -> str:
        indent, var, shape, radius, edges = m.groups()
        return (
            f"{indent}if {edges}:\n"
            f"{indent}    {var} = {shape}.makeFillet({radius}, {edges})\n"
            f"{indent}else:\n"
            f"{indent}    {var} = {shape}"
        )

    def _repl_chamfer(m: re.Match) -> str:
        indent, var, shape, radius, edges = m.groups()
        return (
            f"{indent}if {edges}:\n"
            f"{indent}    {var} = {shape}.makeChamfer({radius}, {edges})\n"
            f"{indent}else:\n"
            f"{indent}    {var} = {shape}"
        )

    code = _FILLET_RE.sub(_repl_fillet, code)
    code = _CHAMFER_RE.sub(_repl_chamfer, code)
    return code


# ------------------------------------------------------------------ #
# 5. Fix Units.RADIAN / Units.Degree hallucinations                  #
# ------------------------------------------------------------------ #

# Models hallucinate ``Units.RADIAN``, ``Units.DEGREE``, ``Units.Quantity(x,"rad")``
# FreeCAD has ``FreeCAD.Units.Radian`` (capital R) in *some* builds, but
# the safest portable approach is plain ``math.radians()`` / ``math.degrees()``.
_UNITS_RADIAN_RE = re.compile(r"\bUnits\.RADIAN\b")
_UNITS_DEGREE_RE = re.compile(r"\bUnits\.DEGREE\b")
_UNITS_RAD_RE    = re.compile(r"\bUnits\.Radian\b")
_UNITS_DEG_RE    = re.compile(r"\bUnits\.Degree\b")
# ``x * Units.RADIAN`` pattern → ``math.radians(x)`` is not straightforward
# because RADIAN would be 1.0 (identity).  Safest: replace the constant
# with 1.0 so ``45 * Units.RADIAN`` becomes ``45 * 1.0`` (= 45 radians, which
# is what the user meant).  But usually models write it WRONG: they mean
# degrees and multiply by RADIAN expecting a conversion.
# Strategy: replace ``Units.RADIAN`` → ``(math.pi / 180)``  (deg→rad factor)
# and ``Units.DEGREE`` → ``1.0``  (already degrees).
_IMPORT_UNITS_RE = re.compile(r"^\s*import\s+Units\b.*$", re.MULTILINE)


def _fix_units_constants(code: str) -> str:
    """Replace hallucinated ``Units.RADIAN`` / ``Units.DEGREE`` with math equivalents."""
    changed = False
    if _UNITS_RADIAN_RE.search(code) or _UNITS_RAD_RE.search(code):
        code = _UNITS_RADIAN_RE.sub("(math.pi / 180)", code)
        code = _UNITS_RAD_RE.sub("(math.pi / 180)", code)
        changed = True
    if _UNITS_DEGREE_RE.search(code) or _UNITS_DEG_RE.search(code):
        code = _UNITS_DEGREE_RE.sub("1.0", code)
        code = _UNITS_DEG_RE.sub("1.0", code)
        changed = True
    if changed:
        # Remove ``import Units`` — it doesn't exist as a standalone module
        code = _IMPORT_UNITS_RE.sub("", code)
        # Ensure ``import math``
        if not re.search(r"^\s*import\s+math\b", code, re.MULTILINE):
            code = "import math\n" + code
    return code


# ------------------------------------------------------------------ #
# 6. Strip App.Units.Quantity() — use plain floats                    #
# ------------------------------------------------------------------ #

# Models produce ``App.Units.Quantity(10, "mm")`` or ``App.Units.Quantity("10 mm")``
# then mix them in arithmetic causing "Unit mismatch in minus operation".
# Strategy: ``App.Units.Quantity(10, "mm")`` → ``10``
#           ``App.Units.Quantity("10 mm")``  → ``10``
#           ``FreeCAD.Units.Quantity(...)``   → same treatment

# Prefix pattern: App.Units. | FreeCAD.Units. | Units.  (bare, after `from FreeCAD import Units`)
_QTY_PFX = r"(?:(?:App|FreeCAD)\.)?Units\.Quantity"

# Two-arg form: Quantity(number_or_expr, "unit")
_QUANTITY_2ARG_RE = re.compile(
    _QTY_PFX + r"\s*\(\s*"
    r"([^,\"']+?)"                  # group 1: the numeric value / expression
    r"\s*,\s*[\"'][^\"']*[\"']\s*\)"
    r"(?:\.Value)?",                # optional .Value accessor
)
# One-arg string form: Quantity("10 mm")
_QUANTITY_1ARG_RE = re.compile(
    _QTY_PFX + r"\s*\(\s*"
    r"[\"']"
    r"([\d.eE+\-]+)"               # group 1: numeric part
    r"\s+[a-zA-Z/°]+[\"']\s*\)"
    r"(?:\.Value)?",
)
# Bare Quantity(number) — no unit string, just a passthrough
_QUANTITY_BARE_RE = re.compile(
    _QTY_PFX + r"\s*\(\s*"
    r"([\d.eE+\-]+)"
    r"\s*\)"
    r"(?:\.Value)?",
)


def _strip_quantity(code: str) -> str:
    """Replace ``App.Units.Quantity(10, "mm")`` → ``10`` (plain float).

    Handles all prefix forms: ``App.Units.Quantity``, ``FreeCAD.Units.Quantity``,
    and bare ``Units.Quantity`` (from ``from FreeCAD import Units``).
    Also strips trailing ``.Value`` accessor.

    FreeCAD properties already expect floats in the document's unit system (mm).
    Using Quantity objects in arithmetic causes ArithmeticError on unit mismatch.
    """
    code = _QUANTITY_2ARG_RE.sub(r"\1", code)
    code = _QUANTITY_1ARG_RE.sub(r"\1", code)
    code = _QUANTITY_BARE_RE.sub(r"\1", code)
    return code


# ------------------------------------------------------------------ #
# 7. Fix null-shape risks: ensure shapes are validated                #
# ------------------------------------------------------------------ #

# Models produce code that chains shape operations without null-checks.
# ``Part.Wire(edges)`` with non-connected edges → null shape.
# ``Part.Face(wire)`` on an open wire → null shape.
# ``Part.makeLoft([wires])`` with bad profiles → null shape.
_WIRE_FACE_RE = re.compile(
    r"\b(Part\.Wire|Part\.Face|Part\.makeLoft|Part\.makePipe|"
    r"Part\.makeSweepSurface|Part\.makeFilledFace)\b"
)


def _add_null_shape_guard(code: str) -> str:
    """Add a reminder comment about null-shape checks when risky calls are used."""
    if not _WIRE_FACE_RE.search(code):
        return code
    if "isNull()" in code or "isValid()" in code:
        return code  # already has checks
    hint = (
        "# IMPORTANT: Wire/Face/Loft can produce Null shapes if geometry is invalid.\n"
        "# After construction, check: if shape.isNull(): raise ValueError('Null shape')\n"
    )
    return hint + code


# ------------------------------------------------------------------ #
# 8. Fix common API mistakes                                         #
# ------------------------------------------------------------------ #

# Models sometimes write App.ActiveDocument.addObject() without checking
_NO_DOC_ADD_RE = re.compile(
    r"App\.ActiveDocument\.addObject\s*\(",
)


def _fix_active_doc_usage(code: str) -> str:
    """Replace bare ``App.ActiveDocument.addObject`` with ``doc.addObject`` when doc exists."""
    if _DOC_ASSIGN_RE.search(code):
        code = _NO_DOC_ADD_RE.sub("doc.addObject(", code)
    return code


# ------------------------------------------------------------------ #
# 9. OCC error wrapper — add try/except around risky operations       #
# ------------------------------------------------------------------ #

_OCC_RISKY = re.compile(
    r"\b(makeFillet|makeChamfer|makePipe|makeLoft|makeRevolution|"
    r"makeShell|makeSolid|makeThickness)\b"
)


def _add_occ_error_context(code: str) -> str:
    """If the code uses OCC-risky operations and has no try/except, add context."""
    if not _OCC_RISKY.search(code):
        return code
    if re.search(r"^\s*try:", code, re.MULTILINE):
        return code  # user already has error handling
    # Don't wrap — just add a helpful comment at the top
    if "Part.OCCError" not in code:
        hint = (
            "# Note: OCC operations (fillet, chamfer, loft...) can raise Part.OCCError\n"
            "# if edges are invalid or radius is too large.  Guard with try/except.\n"
        )
        code = hint + code
    return code


# ------------------------------------------------------------------ #
# 10. Fix ViewObject access in headless/macro mode                    #
# ------------------------------------------------------------------ #

_VIEW_OBJ_RE = re.compile(
    r"^(\s*)(\w+)\.ViewObject\.(\w+)\s*=\s*(.+)$",
    re.MULTILINE,
)


def _guard_view_object(code: str) -> str:
    """Wrap ``obj.ViewObject.X = Y`` in a try/except for headless FreeCAD."""
    def _repl(m: re.Match) -> str:
        indent, obj, attr, value = m.groups()
        return (
            f"{indent}try:\n"
            f"{indent}    {obj}.ViewObject.{attr} = {value}\n"
            f"{indent}except Exception:\n"
            f"{indent}    pass  # ViewObject unavailable in headless mode"
        )
    return _VIEW_OBJ_RE.sub(_repl, code)


# ------------------------------------------------------------------ #
# 11. Fix hallucinated Part API names                                  #
# ------------------------------------------------------------------ #

# LLMs invent Part.makeSweepPipe, Part.makeSweep, Part.makeHelix2, etc.
# Map them to real FreeCAD Part API equivalents.
_FAKE_API_MAP: dict[str, str] = {
    "Part.makeSweepPipe":   "Part.makePipe",
    "Part.makeSweep":       "Part.makePipe",
    "Part.makePipeSweep":   "Part.makePipe",
    "Part.makeSweepShape":  "Part.makePipe",
    "Part.makeHelix2":      "Part.makeHelix",
    "Part.makePrism2":      "Part.makePrism",
    "Part.makeRuledSurface2": "Part.makeRuledSurface",
}

_FAKE_API_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _FAKE_API_MAP) + r")\b"
)


def _fix_hallucinated_api(code: str) -> str:
    """Replace non-existent Part.makeXxx calls with real equivalents."""
    def _repl(m: re.Match) -> str:
        return _FAKE_API_MAP[m.group(1)]
    return _FAKE_API_RE.sub(_repl, code)


# ------------------------------------------------------------------ #
# PUBLIC API                                                          #
# ------------------------------------------------------------------ #

def sanitize_freecad_code(code: str) -> str:
    """Best-effort rewrite of common FreeCAD code issues.

    Applied in order:
    1. Auto-inject missing imports (FreeCAD, Part, Draft, etc.)
    2. Auto-inject ``doc = ...`` if missing
    3. Fix ``Units.RADIAN`` / ``Units.DEGREE`` hallucinations
    4. Strip ``App.Units.Quantity(10, "mm")`` → plain float ``10``
    5. Fix hallucinated API names (makeSweepPipe → makePipe, etc.)
    6. Normalise ``App.ActiveDocument.addObject`` to ``doc.addObject``
    7. Guard ``makeFillet`` / ``makeChamfer`` with empty-edge check
    8. Add null-shape guard comments
    9. Guard ``ViewObject`` access for headless mode
    10. Add OCC error context comment
    11. Auto-inject ``doc.recompute()`` at end if missing
    """
    code = _auto_inject_imports(code)
    code = _auto_inject_doc(code)
    code = _fix_units_constants(code)
    code = _strip_quantity(code)
    code = _fix_hallucinated_api(code)
    code = _fix_active_doc_usage(code)
    code = _guard_fillet_chamfer(code)
    code = _add_null_shape_guard(code)
    code = _guard_view_object(code)
    code = _add_occ_error_context(code)
    code = _auto_inject_recompute(code)
    return code
