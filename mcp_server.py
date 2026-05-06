#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
Unified MCP Server — "une seule appli pour les unifier tous"
============================================================
A Model Context Protocol (MCP) server that bridges Claude Desktop, Cursor,
and any MCP-compatible AI client to multiple creative applications:

    Blender · FreeCAD · GIMP · Inkscape · Photoshop

Architecture
------------
Each application runs a TCP addon/server on its own port:
    Blender     -> port 9876  (blender_mcp_addon.py)
    FreeCAD     -> port 9877  (freecad_mcp_addon.py)
    GIMP        -> port 9878  (gimp_mcp_addon.py)
    Inkscape    -> port 9879  (inkscape_mcp_server.py)
    Photoshop   -> port 9880  (photoshop_mcp_server.py)

This MCP server exposes them as unified tools over stdio JSON-RPC:
    execute_blender_code
    execute_freecad_code
    execute_gimp_code
    execute_inkscape_code
    execute_photoshop_code
    ping_all

Claude Desktop / Cursor config (claude_desktop_config.json):
    {
      "mcpServers": {
        "creative-suite": {
          "command": "python",
          "args": ["path/to/UNIFICATION/mcp_server.py"]
        }
      }
    }

Usage
-----
    python mcp_server.py              # stdio mode (for Claude/Cursor)
    python mcp_server.py --test       # test connectivity to all apps
"""

from __future__ import annotations

import json
import socket
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Application registry
# ---------------------------------------------------------------------------

APPS = {
    "blender": {
        "name": "Blender",
        "port": 9876,
        "description": "Execute Python (bpy) code inside Blender",
        "language": "python",
    },
    "freecad": {
        "name": "FreeCAD",
        "port": 9877,
        "description": "Execute Python (FreeCAD/Part/Draft) code inside FreeCAD",
        "language": "python",
    },
    "gimp": {
        "name": "GIMP",
        "port": 9878,
        "description": "Execute Python-Fu code inside GIMP",
        "language": "python",
    },
    "inkscape": {
        "name": "Inkscape",
        "port": 9879,
        "description": "Execute Python code for SVG manipulation (lxml/inkex + Inkscape CLI)",
        "language": "python",
    },
    "photoshop": {
        "name": "Photoshop",
        "port": 9880,
        "description": "Execute Python/ExtendScript code to control Adobe Photoshop",
        "language": "python",
    },
}

HOST = "127.0.0.1"
TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# TCP client — same protocol as BlenderClient
# ---------------------------------------------------------------------------

def send_code(app_key: str, code: str, timeout: float = TIMEOUT) -> dict:
    """Send code to an application's TCP addon and return the result."""
    app = APPS[app_key]
    port = app["port"]
    payload = json.dumps({"type": "execute", "code": code})

    try:
        with socket.create_connection((HOST, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload.encode("utf-8") + b"\x00")
            buf = bytearray()
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\x00" in chunk:
                    break
        raw = bytes(buf).rstrip(b"\x00").decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {"status": "error", "message": "Empty response"}
    except ConnectionRefusedError:
        return {
            "status": "error",
            "message": f"{app['name']} is not running or its MCP addon is not started (port {port})",
        }
    except Exception as exc:
        return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}


def ping(app_key: str) -> bool:
    """Check if an application's MCP addon is reachable."""
    try:
        result = send_code(app_key, "result = 'pong'", timeout=3.0)
        return result.get("status") == "ok" and result.get("result") == "pong"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MCP Protocol — JSON-RPC 2.0 over stdio
# ---------------------------------------------------------------------------

SERVER_INFO = {
    "name": "creative-suite-mcp",
    "version": "1.0.0",
}

CAPABILITIES = {
    "tools": {},
}


def _build_tools() -> list[dict]:
    """Build the MCP tool definitions."""
    tools = []

    for key, app in APPS.items():
        tools.append({
            "name": f"execute_{key}_code",
            "description": (
                f"{app['description']}. "
                f"Send {app['language']} code to {app['name']} via its TCP MCP addon (port {app['port']}). "
                f"The code is executed inside {app['name']}'s runtime with full API access. "
                f"Set `result = <value>` in your code to return data."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": f"The {app['language']} code to execute inside {app['name']}",
                    },
                },
                "required": ["code"],
            },
        })

    # Unified ping tool
    tools.append({
        "name": "ping_all",
        "description": (
            "Check which creative applications are currently running and reachable. "
            "Returns the connection status for Blender, FreeCAD, GIMP, Inkscape, and Photoshop."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    })

    # Get scene/document info
    tools.append({
        "name": "get_app_status",
        "description": (
            "Get detailed status and basic document/scene info from a running application."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "enum": list(APPS.keys()),
                    "description": "Which application to query",
                },
            },
            "required": ["app"],
        },
    })

    return tools


def _handle_tool_call(name: str, arguments: dict) -> list[dict]:
    """Execute a tool call and return MCP content blocks."""

    # execute_<app>_code
    for key in APPS:
        if name == f"execute_{key}_code":
            code = arguments.get("code", "")
            result = send_code(key, code)

            parts = []
            if result.get("stdout"):
                parts.append(f"[stdout]\n{result['stdout']}")
            if result.get("result") is not None:
                parts.append(f"[result]\n{result['result']!r}")
            if result.get("message"):
                parts.append(f"[error]\n{result['message']}")
            if not parts:
                parts.append(f"[status] {result.get('status', 'unknown')}")

            text = "\n\n".join(parts)
            is_error = result.get("status") != "ok"
            return [{"type": "text", "text": text}], is_error

    # ping_all
    if name == "ping_all":
        lines = []
        for key, app in APPS.items():
            ok = ping(key)
            status = "ONLINE" if ok else "offline"
            icon = "+" if ok else "-"
            lines.append(f"  [{icon}] {app['name']:12s} port {app['port']}  {status}")
        text = "Creative Suite Status:\n" + "\n".join(lines)
        return [{"type": "text", "text": text}], False

    # get_app_status
    if name == "get_app_status":
        app_key = arguments.get("app", "")
        if app_key not in APPS:
            return [{"type": "text", "text": f"Unknown app: {app_key}"}], True

        app = APPS[app_key]
        ok = ping(app_key)
        if not ok:
            return [{"type": "text", "text": f"{app['name']} is not reachable on port {app['port']}"}], True

        # Get basic info from each app
        info_code = {
            "blender": "import bpy; result = {'file': bpy.data.filepath or '(unsaved)', 'objects': len(bpy.data.objects), 'scene': bpy.context.scene.name}",
            "freecad": "import FreeCAD; doc = FreeCAD.ActiveDocument; result = {'file': doc.FileName if doc else '(none)', 'objects': len(doc.Objects) if doc else 0, 'label': doc.Label if doc else '(none)'}",
            "gimp": "result = 'GIMP connected'",
            "inkscape": "result = 'Inkscape server connected'",
            "photoshop": "result = get_document_info()",
        }

        result = send_code(app_key, info_code.get(app_key, "result = 'connected'"))
        text = f"{app['name']} (port {app['port']}): ONLINE\n{json.dumps(result, indent=2, default=str)}"
        return [{"type": "text", "text": text}], False

    return [{"type": "text", "text": f"Unknown tool: {name}"}], True


# ---------------------------------------------------------------------------
# JSON-RPC stdio loop
# ---------------------------------------------------------------------------

def _read_message() -> dict | None:
    """Read a JSON-RPC message from stdin."""
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _write_message(msg: dict) -> None:
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def run_stdio() -> None:
    """Main MCP server loop — reads JSON-RPC from stdin, writes to stdout."""
    # Log to stderr so it doesn't interfere with the protocol
    sys.stderr.write("[MCP] Creative Suite MCP server starting (stdio mode)\n")
    sys.stderr.flush()

    while True:
        try:
            msg = _read_message()
            if msg is None:
                break  # EOF

            method = msg.get("method", "")
            msg_id = msg.get("id")
            params = msg.get("params", {})

            # --- initialize ---
            if method == "initialize":
                _write_message(_jsonrpc_response(msg_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": CAPABILITIES,
                    "serverInfo": SERVER_INFO,
                }))

            # --- initialized (notification) ---
            elif method == "notifications/initialized":
                pass  # no response needed

            # --- tools/list ---
            elif method == "tools/list":
                _write_message(_jsonrpc_response(msg_id, {
                    "tools": _build_tools(),
                }))

            # --- tools/call ---
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                content, is_error = _handle_tool_call(tool_name, arguments)
                _write_message(_jsonrpc_response(msg_id, {
                    "content": content,
                    "isError": is_error,
                }))

            # --- ping ---
            elif method == "ping":
                _write_message(_jsonrpc_response(msg_id, {}))

            # --- unknown method ---
            else:
                if msg_id is not None:
                    _write_message(_jsonrpc_error(msg_id, -32601, f"Unknown method: {method}"))

        except json.JSONDecodeError:
            continue
        except Exception as exc:
            sys.stderr.write(f"[MCP] Error: {exc}\n")
            sys.stderr.flush()


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def test_connectivity() -> None:
    """Test connectivity to all applications."""
    print()
    print("  Creative Suite MCP — Connectivity Test")
    print("  " + "=" * 42)
    print()

    any_online = False
    for key, app in APPS.items():
        ok = ping(key)
        status = "ONLINE" if ok else "offline"
        icon = "[+]" if ok else "[-]"
        print(f"  {icon} {app['name']:12s}  port {app['port']}  ->  {status}")
        if ok:
            any_online = True

    print()
    if any_online:
        print("  Ready! Add this to claude_desktop_config.json:")
        print()
        print('  {')
        print('    "mcpServers": {')
        print('      "creative-suite": {')
        print(f'        "command": "python",')
        print(f'        "args": ["{Path(__file__).resolve()}"]')
        print('      }')
        print('    }')
        print('  }')
    else:
        print("  No applications detected. Start your apps and their MCP addons first.")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path

    if "--test" in sys.argv:
        test_connectivity()
    elif "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
    else:
        run_stdio()
