#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
Inkscape MCP Server
===================
A standalone TCP server (port 9879) that lets UNIFICATION, Claude,
Cursor, or any MCP-compatible client generate/manipulate SVG files
and drive Inkscape via its command-line interface.

Unlike Blender/FreeCAD/GIMP which host the server inside their process,
Inkscape doesn't support persistent plugins. This server runs alongside
Inkscape and:
  1. Executes Python code that manipulates SVG documents via lxml/inkex
  2. Can invoke Inkscape CLI for rendering, export, and batch processing
  3. Returns results in the same JSON+\\0 protocol as all other MCP addons

Protocol  (identical to the Blender MCP addon)
--------
- Transport : raw TCP, null-byte (\\0) delimited JSON frames
- Request   : {"type": "execute", "code": "<python>"}
- Response  : {"status": "ok"|"error", "result": ..., "stdout": "...",
               "message": "<traceback on error>"}

Requirements
------------
    pip install lxml
    # Optional: pip install inkex  (bundled with Inkscape 1.x)

Usage
-----
    python inkscape_mcp_server.py [--port 9879]

The server exposes these pre-loaded modules in the execution namespace:
  - lxml.etree, lxml.builder
  - inkex (if available — Inkscape's Python extension library)
  - subprocess (for calling `inkscape` CLI)
  - os, shutil, tempfile, pathlib
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
from io import StringIO
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PORT   = 9879
_HOST           = "localhost"
_CLIENT_TIMEOUT = 300.0

# ---------------------------------------------------------------------------
# Inkscape CLI detection
# ---------------------------------------------------------------------------

def _find_inkscape() -> str | None:
    """Find the Inkscape executable on the system."""
    # Check PATH first
    ink = shutil.which("inkscape")
    if ink:
        return ink

    # Common install locations
    candidates = []
    if sys.platform == "win32":
        for pf in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]:
            if pf:
                candidates.append(os.path.join(pf, "Inkscape", "bin", "inkscape.exe"))
                candidates.append(os.path.join(pf, "Inkscape", "inkscape.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Inkscape.app/Contents/MacOS/inkscape")
    else:  # Linux
        candidates.extend([
            "/usr/bin/inkscape",
            "/usr/local/bin/inkscape",
            "/snap/bin/inkscape",
            "/var/lib/flatpak/exports/bin/org.inkscape.Inkscape",
        ])

    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


_INKSCAPE_BIN = _find_inkscape()


# ---------------------------------------------------------------------------
# SVG helpers pre-loaded in execution namespace
# ---------------------------------------------------------------------------

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

_BLANK_SVG = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{_SVG_NS}"
     xmlns:xlink="{_XLINK_NS}"
     xmlns:inkscape="{_INKSCAPE_NS}"
     width="800" height="600" viewBox="0 0 800 600">
</svg>
"""


def inkscape_run(*args: str, input_svg: str | None = None, timeout: float = 60.0) -> str:
    """Run Inkscape CLI with the given arguments. Returns stdout."""
    if _INKSCAPE_BIN is None:
        raise FileNotFoundError(
            "Inkscape not found on this system. Install it or add it to PATH."
        )
    cmd = [_INKSCAPE_BIN, *args]
    result = subprocess.run(
        cmd,
        input=input_svg.encode("utf-8") if input_svg else None,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Inkscape exited with code {result.returncode}: {stderr}")
    return result.stdout.decode("utf-8", errors="replace")


def svg_to_png(svg_path: str, png_path: str, dpi: int = 96) -> str:
    """Export an SVG file to PNG via Inkscape CLI."""
    inkscape_run(
        svg_path,
        f"--export-filename={png_path}",
        f"--export-dpi={dpi}",
        "--export-type=png",
    )
    return png_path


def svg_to_pdf(svg_path: str, pdf_path: str) -> str:
    """Export an SVG file to PDF via Inkscape CLI."""
    inkscape_run(
        svg_path,
        f"--export-filename={pdf_path}",
        "--export-type=pdf",
    )
    return pdf_path


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------

def _execute(code: str) -> dict:
    """Execute Python code in a namespace pre-loaded with SVG tools."""
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = cap = StringIO()
    try:
        ns = {
            "result": None,
            # stdlib
            "os": os,
            "subprocess": subprocess,
            "tempfile": tempfile,
            "Path": Path,
            # SVG namespaces
            "SVG_NS": _SVG_NS,
            "XLINK_NS": _XLINK_NS,
            "INKSCAPE_NS": _INKSCAPE_NS,
            "BLANK_SVG": _BLANK_SVG,
            # Inkscape helpers
            "inkscape_run": inkscape_run,
            "svg_to_png": svg_to_png,
            "svg_to_pdf": svg_to_pdf,
            "INKSCAPE_BIN": _INKSCAPE_BIN,
        }

        # lxml for SVG manipulation
        try:
            from lxml import etree
            from lxml.builder import E, ElementMaker
            ns["etree"] = etree
            ns["E"] = E
            ns["ElementMaker"] = ElementMaker
        except ImportError:
            pass

        # inkex — Inkscape's Python extension library
        try:
            import inkex
            ns["inkex"] = inkex
        except ImportError:
            pass

        exec(compile(code, "<mcp>", "exec"), ns)
        return {
            "status": "ok",
            "result": ns.get("result"),
            "stdout": cap.getvalue(),
        }
    except Exception:
        return {
            "status": "error",
            "message": traceback.format_exc(),
            "stdout": cap.getvalue(),
        }
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


# ---------------------------------------------------------------------------
# TCP Server
# ---------------------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
    try:
        buf = bytearray()
        conn.settimeout(_CLIENT_TIMEOUT)
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
            if b"\0" in buf:
                break

        if not buf:
            return

        raw = buf.split(b"\0")[0]
        req = json.loads(raw.decode("utf-8"))
        code = req.get("code", "")

        response = _execute(code)
        conn.sendall(
            (json.dumps(response, default=str) + "\0").encode("utf-8")
        )

    except Exception as exc:
        try:
            conn.sendall(
                (json.dumps({"status": "error", "message": str(exc)}) + "\0").encode("utf-8")
            )
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve(port: int = _DEFAULT_PORT) -> None:
    """Run the server in the foreground (blocking)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((_HOST, port))
    srv.listen(5)

    ink_status = f"Inkscape CLI: {_INKSCAPE_BIN}" if _INKSCAPE_BIN else "Inkscape CLI: NOT FOUND"
    print(f"[Inkscape MCP] Server ready on port {port}")
    print(f"[Inkscape MCP] {ink_status}")
    print(f"[Inkscape MCP] Protocol: TCP / JSON+\\0  (same as Blender MCP)")
    print(f"[Inkscape MCP] Press Ctrl+C to stop")

    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[Inkscape MCP] Shutting down...")
    finally:
        srv.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inkscape MCP Server")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT,
                        help=f"TCP port (default {_DEFAULT_PORT})")
    args = parser.parse_args()
    serve(args.port)
