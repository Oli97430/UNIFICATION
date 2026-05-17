#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
Unified MCP Server v2 — "une seule appli pour les unifier tous"
================================================================
A Model Context Protocol (MCP) server that bridges Claude Desktop, Cursor,
Claude Code and any MCP-compatible AI client to multiple creative applications:

    Blender · FreeCAD · GIMP · Inkscape · Photoshop

Architecture
------------
Each application runs a TCP addon/server on its own port:
    Blender     -> port 9876  (blender_mcp_addon.py)
    FreeCAD     -> port 9877  (freecad_mcp_addon.py)
    GIMP        -> port 9878  (gimp_mcp_addon.py)
    Inkscape    -> port 9879  (inkscape_mcp_server.py)
    Photoshop   -> port 9880  (photoshop_mcp_server.py)

Tools (v2)
----------
    execute_blender_code     — run Python in Blender
    execute_freecad_code     — run Python in FreeCAD
    execute_gimp_code        — run Python in GIMP
    execute_inkscape_code    — run Python in Inkscape
    execute_photoshop_code   — run Python in Photoshop
    ping_all                 — check connectivity + versions
    get_app_status           — detailed doc/scene info
    batch_execute            — run code in multiple apps at once
    validate_code            — syntax-check Python before sending

Usage
-----
    python mcp_server.py              # stdio mode (for Claude/Cursor)
    python mcp_server.py --test       # test connectivity to all apps
"""

from __future__ import annotations

import ast
import json
import socket
import sys
import threading
import time
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
        "timeout": 60.0,
        "version_code": "import bpy; result = bpy.app.version_string",
    },
    "freecad": {
        "name": "FreeCAD",
        "port": 9877,
        "description": "Execute Python (FreeCAD/Part/Draft) code inside FreeCAD",
        "language": "python",
        "timeout": 90.0,  # boolean ops can be slow
        "version_code": "import FreeCAD; result = FreeCAD.Version()[0] + '.' + FreeCAD.Version()[1]",
    },
    "gimp": {
        "name": "GIMP",
        "port": 9878,
        "description": "Execute Python-Fu code inside GIMP",
        "language": "python",
        "timeout": 60.0,
        "version_code": "result = 'connected'",
    },
    "inkscape": {
        "name": "Inkscape",
        "port": 9879,
        "description": "Execute Python code for SVG manipulation (lxml/inkex + Inkscape CLI)",
        "language": "python",
        "timeout": 60.0,
        "version_code": "result = 'connected'",
    },
    "photoshop": {
        "name": "Photoshop",
        "port": 9880,
        "description": "Execute Python/ExtendScript code to control Adobe Photoshop",
        "language": "python",
        "timeout": 60.0,
        "version_code": "result = 'connected'",
    },
}

HOST = "127.0.0.1"
MAX_RETRIES = 1
PING_TIMEOUT = 3.0

SERVER_INFO = {
    "name": "creative-suite-mcp",
    "version": "2.0.0",
}

CAPABILITIES = {
    "tools": {},
    "logging": {},
}


# ---------------------------------------------------------------------------
# TCP client — with retry and configurable timeout
# ---------------------------------------------------------------------------

def send_code(app_key: str, code: str, timeout: float | None = None,
              retries: int = MAX_RETRIES) -> dict:
    """Send code to an application's TCP addon and return the result.

    Retries once on timeout/connection failure before giving up.
    """
    app = APPS[app_key]
    port = app["port"]
    effective_timeout = timeout or app.get("timeout", 60.0)
    payload = json.dumps({"type": "execute", "code": code})

    last_error = ""
    for attempt in range(1 + retries):
        try:
            with socket.create_connection((HOST, port), timeout=effective_timeout) as sock:
                sock.settimeout(effective_timeout)
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
                "message": (
                    f"{app['name']} is not running or its MCP addon is not started (port {port}).\n"
                    f"Start {app['name']} and load the MCP addon, then retry."
                ),
            }
        except (TimeoutError, socket.timeout) as exc:
            last_error = f"Timeout after {effective_timeout}s"
            if attempt < retries:
                _log(f"[retry] {app['name']} timed out, retrying ({attempt+1}/{retries})...")
                time.sleep(0.5)
                continue
            return {
                "status": "error",
                "message": (
                    f"{app['name']} timed out after {effective_timeout}s (tried {1+retries}x).\n"
                    f"The operation may be too heavy. Try splitting into smaller steps."
                ),
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                _log(f"[retry] {app['name']} error: {last_error}, retrying...")
                time.sleep(0.5)
                continue
            return {"status": "error", "message": last_error}

    return {"status": "error", "message": last_error}


def ping(app_key: str) -> dict:
    """Check if an application's MCP addon is reachable. Returns status dict."""
    app = APPS[app_key]
    try:
        result = send_code(app_key, app.get("version_code", "result = 'pong'"),
                           timeout=PING_TIMEOUT, retries=0)
        if result.get("status") == "ok":
            return {"online": True, "version": result.get("result", "unknown")}
        return {"online": False, "error": result.get("message", "unknown")}
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def ping_bool(app_key: str) -> bool:
    """Simple boolean ping for backward compatibility."""
    return ping(app_key).get("online", False)


# ---------------------------------------------------------------------------
# Code validation
# ---------------------------------------------------------------------------

def validate_python(code: str) -> dict:
    """Syntax-check Python code without executing it."""
    try:
        ast.parse(code)
        return {"valid": True, "message": "Syntax OK"}
    except SyntaxError as exc:
        return {
            "valid": False,
            "message": f"SyntaxError at line {exc.lineno}: {exc.msg}",
            "line": exc.lineno,
            "offset": exc.offset,
        }


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Log to stderr (doesn't interfere with stdio JSON-RPC)."""
    sys.stderr.write(f"[MCP] {msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# MCP Protocol — JSON-RPC 2.0 over stdio
# ---------------------------------------------------------------------------

def _build_tools() -> list[dict]:
    """Build the MCP tool definitions."""
    tools = []

    # Per-app execute tools
    for key, app in APPS.items():
        tools.append({
            "name": f"execute_{key}_code",
            "description": (
                f"{app['description']}. "
                f"Send {app['language']} code to {app['name']} via TCP (port {app['port']}). "
                f"Executed inside {app['name']}'s runtime with full API access. "
                f"Set `result = <value>` to return data. "
                f"Timeout: {app['timeout']:.0f}s (auto-retry once on failure)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": f"The {app['language']} code to execute inside {app['name']}",
                    },
                    "timeout": {
                        "type": "number",
                        "description": f"Override timeout in seconds (default: {app['timeout']:.0f})",
                    },
                },
                "required": ["code"],
            },
        })

    # Unified ping tool (with versions)
    tools.append({
        "name": "ping_all",
        "description": (
            "Check which creative applications are currently running and reachable. "
            "Returns connection status AND version for each app: "
            "Blender, FreeCAD, GIMP, Inkscape, and Photoshop."
        ),
        "inputSchema": {"type": "object", "properties": {}},
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

    # Batch execute
    tools.append({
        "name": "batch_execute",
        "description": (
            "Execute code in multiple creative apps simultaneously. "
            "Useful for syncing operations across apps (e.g. export from Blender, import in FreeCAD). "
            "Each task runs in parallel; results are collected."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "List of {app, code} objects to execute in parallel",
                    "items": {
                        "type": "object",
                        "properties": {
                            "app": {
                                "type": "string",
                                "enum": list(APPS.keys()),
                                "description": "Target application",
                            },
                            "code": {
                                "type": "string",
                                "description": "Python code to execute",
                            },
                        },
                        "required": ["app", "code"],
                    },
                },
            },
            "required": ["tasks"],
        },
    })

    # Validate code
    tools.append({
        "name": "validate_code",
        "description": (
            "Syntax-check Python code without executing it. "
            "Useful to catch typos before sending to an app."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to validate",
                },
            },
            "required": ["code"],
        },
    })

    return tools


def _format_result(result: dict) -> str:
    """Format a send_code result into readable text."""
    parts = []
    if result.get("stdout"):
        parts.append(f"[stdout]\n{result['stdout']}")
    if result.get("result") is not None:
        parts.append(f"[result]\n{result['result']!r}")
    if result.get("message"):
        parts.append(f"[error]\n{result['message']}")
    if not parts:
        parts.append(f"[status] {result.get('status', 'unknown')}")
    return "\n\n".join(parts)


def _handle_tool_call(name: str, arguments: dict) -> tuple[list[dict], bool]:
    """Execute a tool call and return (content_blocks, is_error)."""

    # ── execute_<app>_code ──
    for key in APPS:
        if name == f"execute_{key}_code":
            code = arguments.get("code", "")
            timeout = arguments.get("timeout")

            # Pre-validate syntax
            check = validate_python(code)
            if not check["valid"]:
                return [{"type": "text", "text": f"[syntax error]\n{check['message']}"}], True

            result = send_code(key, code, timeout=timeout)
            text = _format_result(result)
            is_error = result.get("status") != "ok"
            return [{"type": "text", "text": text}], is_error

    # ── ping_all (with versions) ──
    if name == "ping_all":
        lines = []
        results = {}

        # Parallel ping for speed
        def _ping_thread(k):
            results[k] = ping(k)

        threads = [threading.Thread(target=_ping_thread, args=(k,)) for k in APPS]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)

        for key, app in APPS.items():
            info = results.get(key, {"online": False, "error": "timeout"})
            if info["online"]:
                ver = info.get("version", "")
                lines.append(f"  [+] {app['name']:12s} port {app['port']}  ONLINE  (v{ver})")
            else:
                lines.append(f"  [-] {app['name']:12s} port {app['port']}  offline")

        text = "Creative Suite Status:\n" + "\n".join(lines)
        return [{"type": "text", "text": text}], False

    # ── get_app_status ──
    if name == "get_app_status":
        app_key = arguments.get("app", "")
        if app_key not in APPS:
            return [{"type": "text", "text": f"Unknown app: {app_key}"}], True

        app = APPS[app_key]
        info = ping(app_key)
        if not info["online"]:
            return [{"type": "text", "text": f"{app['name']} is not reachable on port {app['port']}"}], True

        info_code = {
            "blender": (
                "import bpy; result = {"
                "'file': bpy.data.filepath or '(unsaved)', "
                "'objects': len(bpy.data.objects), "
                "'scene': bpy.context.scene.name, "
                "'version': bpy.app.version_string}"
            ),
            "freecad": (
                "import FreeCAD; doc = FreeCAD.ActiveDocument; result = {"
                "'file': doc.FileName if doc else '(none)', "
                "'objects': len(doc.Objects) if doc else 0, "
                "'label': doc.Label if doc else '(none)', "
                "'version': '.'.join(FreeCAD.Version()[:3])}"
            ),
            "gimp": "result = 'GIMP connected'",
            "inkscape": "result = 'Inkscape server connected'",
            "photoshop": "result = get_document_info()",
        }

        result = send_code(app_key, info_code.get(app_key, "result = 'connected'"))
        text = f"{app['name']} (port {app['port']}): ONLINE\n{json.dumps(result, indent=2, default=str)}"
        return [{"type": "text", "text": text}], False

    # ── batch_execute ──
    if name == "batch_execute":
        tasks = arguments.get("tasks", [])
        if not tasks:
            return [{"type": "text", "text": "No tasks provided"}], True

        results_lock = threading.Lock()
        results_map = {}

        def _exec_task(idx, task):
            app_key = task.get("app", "")
            code = task.get("code", "")
            if app_key not in APPS:
                with results_lock:
                    results_map[idx] = {"app": app_key, "error": f"Unknown app: {app_key}"}
                return
            check = validate_python(code)
            if not check["valid"]:
                with results_lock:
                    results_map[idx] = {"app": app_key, "error": check["message"]}
                return
            result = send_code(app_key, code)
            with results_lock:
                results_map[idx] = {"app": app_key, "result": result}

        threads = []
        for i, task in enumerate(tasks):
            th = threading.Thread(target=_exec_task, args=(i, task))
            threads.append(th)
            th.start()
        for th in threads:
            th.join(timeout=120)

        lines = []
        for i in range(len(tasks)):
            fallback_app = tasks[i].get("app", "?")
            r = results_map.get(i, {"app": fallback_app, "error": "timeout"})
            app_name = APPS.get(r.get("app", ""), {}).get("name", r.get("app", "?"))
            if "error" in r:
                lines.append(f"── {app_name} ── ERROR\n{r['error']}")
            else:
                lines.append(f"── {app_name} ──\n{_format_result(r['result'])}")

        text = "\n\n".join(lines)
        has_error = any("error" in results_map.get(i, {}) for i in range(len(tasks)))
        return [{"type": "text", "text": text}], has_error

    # ── validate_code ──
    if name == "validate_code":
        code = arguments.get("code", "")
        check = validate_python(code)
        text = f"{'OK' if check['valid'] else 'FAIL'}: {check['message']}"
        return [{"type": "text", "text": text}], not check["valid"]

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


def _jsonrpc_response(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _jsonrpc_error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def run_stdio() -> None:
    """Main MCP server loop — reads JSON-RPC from stdin, writes to stdout."""
    _log("Creative Suite MCP server v2.0.0 starting (stdio mode)")

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
                pass

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
            _log(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def test_connectivity() -> None:
    """Test connectivity to all applications."""
    print()
    print("  Creative Suite MCP v2.0.0 — Connectivity Test")
    print("  " + "=" * 48)
    print()

    any_online = False
    for key, app in APPS.items():
        info = ping(key)
        if info["online"]:
            ver = info.get("version", "")
            print(f"  [+] {app['name']:12s}  port {app['port']}  ->  ONLINE  (v{ver})")
            any_online = True
        else:
            print(f"  [-] {app['name']:12s}  port {app['port']}  ->  offline")

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
