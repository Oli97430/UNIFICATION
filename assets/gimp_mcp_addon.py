#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
GIMP MCP Server Plugin
======================
Exposes a local TCP server (port 9878) so that UNIFICATION, Claude,
Cursor, or any MCP-compatible client can send Python-Fu code to execute
inside GIMP and receive the results in real-time.

Protocol  (identical to the Blender MCP addon)
--------
- Transport : raw TCP, null-byte (\\0) delimited JSON frames
- Request   : {"type": "execute", "code": "<python>"}
- Response  : {"status": "ok"|"error", "result": ..., "stdout": "...",
               "message": "<traceback on error>"}

Installation — GIMP 2.10
-------------------------
1. Copy this file to GIMP's plug-ins directory:
   - Windows : %APPDATA%/GIMP/2.10/plug-ins/
   - macOS   : ~/Library/Application Support/GIMP/2.10/plug-ins/
   - Linux   : ~/.config/GIMP/2.10/plug-ins/

2. Make sure the file is executable (Linux/macOS): chmod +x gimp_mcp_addon.py
3. Restart GIMP.
4. Go to Filters -> Python-Fu -> MCP Server Start

Installation — GIMP 3.0+
-------------------------
1. Copy to: ~/.config/GIMP/3.0/plug-ins/gimp_mcp_addon/gimp_mcp_addon.py
   (Note: GIMP 3 requires the plugin in a subfolder with the same name)
2. Restart GIMP.
3. Go to Filters -> MCP Server Start
"""

from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import traceback
from io import StringIO

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PORT    = 9878
_HOST            = "localhost"
_TICK_INTERVAL   = 50   # ms
_CLIENT_TIMEOUT  = 300.0
_EXEC_TIMEOUT    = 30.0

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_server_socket: socket.socket | None = None
_task_queue: queue.Queue | None = None
_result_map: dict = {}
_result_lock = threading.Lock()
_task_counter = [0]
_running = False


# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------

def _execute_code(code: str) -> dict:
    """Execute Python code with GIMP modules in namespace."""
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = cap = StringIO()
    try:
        ns = {"result": None}

        # Inject GIMP modules into namespace
        try:
            import gimp
            ns["gimp"] = gimp
        except ImportError:
            pass
        try:
            from gimp import pdb
            ns["pdb"] = pdb
        except ImportError:
            pass
        try:
            import gimpfu
            ns["gimpfu"] = gimpfu
        except ImportError:
            pass
        try:
            import gimpenums
            ns["gimpenums"] = gimpenums
        except ImportError:
            pass
        # GIMP 3.0+ uses GObject introspection
        try:
            import gi
            gi.require_version("Gimp", "3.0")
            from gi.repository import Gimp, GLib, Gio
            ns["Gimp"] = Gimp
            ns["GLib"] = GLib
            ns["Gio"] = Gio
        except (ImportError, ValueError):
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


def _tick():
    """Drain task queue on the main thread (called via GLib.timeout_add)."""
    global _running
    if not _running or _task_queue is None:
        return False  # stop the timeout

    try:
        while not _task_queue.empty():
            tid, code = _task_queue.get_nowait()
            res = _execute_code(code)
            with _result_lock:
                _result_map[tid] = res
    except Exception:
        pass

    return True  # keep the timeout running


# ---------------------------------------------------------------------------
# Per-connection handler (background thread)
# ---------------------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
    import time

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

        with _result_lock:
            _task_counter[0] += 1
            tid = _task_counter[0]
        _task_queue.put((tid, code))

        deadline = time.monotonic() + _EXEC_TIMEOUT
        while time.monotonic() < deadline:
            with _result_lock:
                if tid in _result_map:
                    response = _result_map.pop(tid)
                    conn.sendall(
                        (json.dumps(response, default=str) + "\0").encode("utf-8")
                    )
                    return
            time.sleep(0.05)

        conn.sendall(
            (json.dumps({"status": "error",
                         "message": f"Execution timed out after {_EXEC_TIMEOUT:.0f}s"})
             + "\0").encode("utf-8")
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


def _accept_loop(srv_sock: socket.socket) -> None:
    while True:
        try:
            conn, _ = srv_sock.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        except Exception:
            break


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def server_start(port: int = _DEFAULT_PORT) -> str:
    global _server_socket, _task_queue, _running

    if _running and _server_socket:
        return f"Already running on port {port}"

    _task_queue = queue.Queue()

    try:
        _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _server_socket.bind((_HOST, port))
        _server_socket.listen(5)
        threading.Thread(target=_accept_loop, args=(_server_socket,), daemon=True).start()
        _running = True

        # Register main-thread timer via GLib (GIMP's event loop)
        try:
            from gi.repository import GLib
            GLib.timeout_add(_TICK_INTERVAL, _tick)
        except ImportError:
            try:
                import gobject
                gobject.timeout_add(_TICK_INTERVAL, _tick)
            except ImportError:
                # Fallback: run tick in a background thread (less safe but works)
                def _bg_tick():
                    import time
                    while _running:
                        _tick()
                        time.sleep(_TICK_INTERVAL / 1000.0)
                threading.Thread(target=_bg_tick, daemon=True).start()

        msg = f"[GIMP MCP] Server ready on port {port}"
        print(msg)
        try:
            import gimp
            gimp.message(msg)
        except Exception:
            pass
        return msg

    except OSError as exc:
        if _server_socket:
            try:
                _server_socket.close()
            except Exception:
                pass
            _server_socket = None
        return f"[GIMP MCP] Failed to start: {exc}"


def server_stop() -> str:
    global _server_socket, _running

    _running = False
    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None

    msg = "[GIMP MCP] Server stopped"
    print(msg)
    return msg


# ---------------------------------------------------------------------------
# GIMP 2.x Plugin Registration
# ---------------------------------------------------------------------------

try:
    from gimpfu import register, main

    def _gimp2_start(image=None, drawable=None):
        server_start()

    def _gimp2_stop(image=None, drawable=None):
        server_stop()

    register(
        "python_fu_mcp_start",
        "Start MCP Server",
        "Start the MCP TCP server so AI tools can control GIMP",
        "Olivier Hoarau", "GPL-3.0", "2026",
        "<Toolbox>/Filters/Python-Fu/MCP Server Start",
        "",
        [],
        [],
        _gimp2_start,
    )

    register(
        "python_fu_mcp_stop",
        "Stop MCP Server",
        "Stop the MCP TCP server",
        "Olivier Hoarau", "GPL-3.0", "2026",
        "<Toolbox>/Filters/Python-Fu/MCP Server Stop",
        "",
        [],
        [],
        _gimp2_stop,
    )

    main()

except ImportError:
    # Not running inside GIMP 2 — either GIMP 3 or standalone
    pass


# ---------------------------------------------------------------------------
# GIMP 3.x Plugin Registration  (GObject-based)
# ---------------------------------------------------------------------------

try:
    import gi
    gi.require_version("Gimp", "3.0")
    gi.require_version("GimpUi", "3.0")
    from gi.repository import Gimp, GObject

    class MCPServerPlugin(Gimp.PlugIn):
        def do_query_procedures(self):
            return ["mcp-server-start", "mcp-server-stop"]

        def do_set_i18n(self, name):
            return False

        def do_create_procedure(self, name):
            if name == "mcp-server-start":
                procedure = Gimp.Procedure.new(
                    self, name, Gimp.PDBProcType.PLUGIN,
                    self._start_run, None
                )
                procedure.set_menu_label("MCP Server Start")
                procedure.add_menu_path("<Image>/Filters")
                procedure.set_documentation(
                    "Start MCP Server",
                    "Start the TCP server for AI tool integration",
                    name
                )
            elif name == "mcp-server-stop":
                procedure = Gimp.Procedure.new(
                    self, name, Gimp.PDBProcType.PLUGIN,
                    self._stop_run, None
                )
                procedure.set_menu_label("MCP Server Stop")
                procedure.add_menu_path("<Image>/Filters")
                procedure.set_documentation(
                    "Stop MCP Server",
                    "Stop the TCP server",
                    name
                )
            return procedure

        def _start_run(self, procedure, config, data):
            server_start()
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS)

        def _stop_run(self, procedure, config, data):
            server_stop()
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS)

    Gimp.main(MCPServerPlugin.__gtype__, sys.argv)

except (ImportError, ValueError):
    # Not running inside GIMP 3 either
    pass

# ---------------------------------------------------------------------------
# Standalone fallback — for testing or manual launch
# ---------------------------------------------------------------------------

if __name__ == "__main__" and "gimp" not in sys.modules and "gi.repository.Gimp" not in sys.modules:
    print("[GIMP MCP] Running in standalone mode (no GIMP integration)")
    server_start()
    try:
        threading.Event().wait()  # block forever
    except KeyboardInterrupt:
        server_stop()
