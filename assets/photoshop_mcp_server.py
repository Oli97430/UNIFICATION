#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
Photoshop MCP Server
====================
A standalone TCP server (port 9880) that lets UNIFICATION, Claude,
Cursor, or any MCP-compatible client send JavaScript (ExtendScript) or
Python automation code to execute inside Adobe Photoshop.

Photoshop is controlled via:
  - **Windows**: COM automation (win32com.client)
  - **macOS**: AppleScript bridge + osascript
  - **Both**: Photoshop's DoJavaScript() method for ExtendScript

Protocol  (identical to the Blender MCP addon)
--------
- Transport : raw TCP, null-byte (\\0) delimited JSON frames
- Request   : {"type": "execute", "code": "<python or javascript>"}
- Response  : {"status": "ok"|"error", "result": ..., "stdout": "...",
               "message": "<traceback on error>"}

Requirements
------------
    Windows: pip install pywin32
    macOS  : (no extra dependencies — uses subprocess + osascript)

Usage
-----
    python photoshop_mcp_server.py [--port 9880]

How code is executed
--------------------
The server receives Python code. Within that code, you can:

1. Use `ps` — the pre-loaded Photoshop COM object (Windows):
       doc = ps.ActiveDocument
       layer = doc.ArtLayers.Add()
       layer.Name = "My Layer"

2. Use `run_jsx(script)` — execute ExtendScript in Photoshop:
       result = run_jsx('app.activeDocument.name')

3. Use `run_action(action_name, action_set)` — run a Photoshop Action:
       run_action("Sepia Toning", "Default Actions")
"""

from __future__ import annotations

import argparse
import json
import os
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

_DEFAULT_PORT   = 9880
_HOST           = "localhost"
_CLIENT_TIMEOUT = 300.0

# ---------------------------------------------------------------------------
# Photoshop bridge — platform-specific
# ---------------------------------------------------------------------------

_ps_app = None  # COM object (Windows) or None (macOS)


def _connect_photoshop():
    """Connect to a running Photoshop instance."""
    global _ps_app

    if sys.platform == "win32":
        try:
            import win32com.client
            _ps_app = win32com.client.Dispatch("Photoshop.Application")
            print(f"[Photoshop MCP] Connected to Photoshop {_ps_app.Version}")
            return True
        except Exception as exc:
            print(f"[Photoshop MCP] Cannot connect to Photoshop via COM: {exc}")
            print("[Photoshop MCP] Make sure Photoshop is running and pywin32 is installed")
            _ps_app = None
            return False

    elif sys.platform == "darwin":
        # On macOS, we use osascript to drive Photoshop
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "Adobe Photoshop" to get version'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"[Photoshop MCP] Connected to Photoshop {version} via AppleScript")
                return True
            else:
                print(f"[Photoshop MCP] Cannot reach Photoshop: {result.stderr.strip()}")
                return False
        except Exception as exc:
            print(f"[Photoshop MCP] AppleScript bridge failed: {exc}")
            return False

    else:
        print("[Photoshop MCP] Photoshop automation requires Windows or macOS")
        return False


def run_jsx(script: str) -> str:
    """Execute ExtendScript (JavaScript) code inside Photoshop.

    Returns the string result of the script.
    """
    global _ps_app

    if sys.platform == "win32":
        if _ps_app is None:
            _connect_photoshop()
        if _ps_app is None:
            raise RuntimeError("Not connected to Photoshop")
        result = _ps_app.DoJavaScript(script)
        return str(result) if result is not None else ""

    elif sys.platform == "darwin":
        # Write JSX to a temp file, execute via osascript
        jsx_path = os.path.join(tempfile.gettempdir(), "_mcp_ps.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(script)
        result = subprocess.run(
            [
                "osascript", "-e",
                f'tell application "Adobe Photoshop" to do javascript file "{jsx_path}"'
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"JSX execution failed: {result.stderr.strip()}")
        return result.stdout.strip()

    raise RuntimeError("Unsupported platform for Photoshop automation")


def run_action(action_name: str, action_set: str) -> None:
    """Run a Photoshop Action by name."""
    jsx = f'app.doAction("{action_name}", "{action_set}");'
    run_jsx(jsx)


def get_document_info() -> dict:
    """Get info about the active Photoshop document."""
    jsx = """
    var doc = app.activeDocument;
    var info = {
        name: doc.name,
        width: doc.width.as('px'),
        height: doc.height.as('px'),
        resolution: doc.resolution,
        mode: doc.mode.toString(),
        layers: doc.layers.length,
        path: doc.fullName ? doc.fullName.fsName : ""
    };
    JSON.stringify(info);
    """
    result = run_jsx(jsx)
    return json.loads(result)


def list_layers() -> list[str]:
    """List all layer names in the active document."""
    jsx = """
    var doc = app.activeDocument;
    var names = [];
    for (var i = 0; i < doc.layers.length; i++) {
        names.push(doc.layers[i].name);
    }
    JSON.stringify(names);
    """
    result = run_jsx(jsx)
    return json.loads(result)


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------

def _execute(code: str) -> dict:
    """Execute Python code with Photoshop helpers in namespace."""
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = cap = StringIO()
    try:
        ns = {
            "result": None,
            # Photoshop bridge
            "ps": _ps_app,
            "run_jsx": run_jsx,
            "run_action": run_action,
            "get_document_info": get_document_info,
            "list_layers": list_layers,
            # stdlib
            "os": os,
            "subprocess": subprocess,
            "tempfile": tempfile,
            "Path": Path,
            "json": json,
        }

        # pywin32 extras (Windows)
        if sys.platform == "win32":
            try:
                import win32com.client
                ns["win32com"] = win32com
                ns["Dispatch"] = win32com.client.Dispatch
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
    """Run the server (blocking)."""
    # Try to connect to Photoshop at startup
    _connect_photoshop()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((_HOST, port))
    srv.listen(5)

    ps_status = "connected" if (_ps_app is not None or sys.platform == "darwin") else "NOT connected"
    print(f"[Photoshop MCP] Server ready on port {port}")
    print(f"[Photoshop MCP] Photoshop: {ps_status}")
    print(f"[Photoshop MCP] Protocol: TCP / JSON+\\0  (same as Blender MCP)")
    print(f"[Photoshop MCP] Press Ctrl+C to stop")

    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[Photoshop MCP] Shutting down...")
    finally:
        srv.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Photoshop MCP Server")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT,
                        help=f"TCP port (default {_DEFAULT_PORT})")
    args = parser.parse_args()
    serve(args.port)
