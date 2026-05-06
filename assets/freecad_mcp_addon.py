# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
FreeCAD MCP Server Addon
========================
Exposes a local TCP server (port 9877) so that UNIFICATION, Claude,
Cursor, or any MCP-compatible client can send Python code to execute
inside FreeCAD and receive the results in real-time.

Protocol  (identical to the Blender MCP addon)
--------
- Transport : raw TCP, null-byte (\\0) delimited JSON frames
- Request   : {"type": "execute", "code": "<python>"}
- Response  : {"status": "ok"|"error", "result": ..., "stdout": "...",
               "message": "<traceback on error>"}

Installation
------------
1. Copy this file to FreeCAD's Macro directory:
   - Windows : %APPDATA%/FreeCAD/Macro/
   - macOS   : ~/Library/Application Support/FreeCAD/Macro/
   - Linux   : ~/.local/share/FreeCAD/Macro/

2. In FreeCAD: Macro -> Macros -> select "freecad_mcp_addon" -> Execute
   Or run from the Python console:
       exec(open("path/to/freecad_mcp_addon.py").read())

3. The server auto-starts and prints the port in the Report View.

Stopping
--------
    from freecad_mcp_addon import server_stop; server_stop()
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

_DEFAULT_PORT    = 9877
_HOST            = "localhost"
_TICK_INTERVAL   = 50        # ms between main-thread ticks (QTimer)
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
_timer = None  # QTimer reference


# ---------------------------------------------------------------------------
# Main-thread execution (via QTimer)
# ---------------------------------------------------------------------------

def _tick():
    """Drain the task queue on FreeCAD's main thread."""
    global _task_queue
    if not _running or _task_queue is None:
        return

    try:
        while not _task_queue.empty():
            tid, code = _task_queue.get_nowait()

            saved_out, saved_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = cap = StringIO()
            try:
                # Build namespace with FreeCAD modules available
                ns = {"result": None}
                try:
                    import FreeCAD
                    ns["FreeCAD"] = FreeCAD
                    ns["App"] = FreeCAD
                except ImportError:
                    pass
                try:
                    import FreeCADGui
                    ns["FreeCADGui"] = FreeCADGui
                    ns["Gui"] = FreeCADGui
                except ImportError:
                    pass
                try:
                    import Part
                    ns["Part"] = Part
                except ImportError:
                    pass
                try:
                    import Draft
                    ns["Draft"] = Draft
                except ImportError:
                    pass
                try:
                    import Mesh
                    ns["Mesh"] = Mesh
                except ImportError:
                    pass
                try:
                    import Sketcher
                    ns["Sketcher"] = Sketcher
                except ImportError:
                    pass
                try:
                    import PartDesign
                    ns["PartDesign"] = PartDesign
                except ImportError:
                    pass

                exec(compile(code, "<mcp>", "exec"), ns)
                res = {
                    "status": "ok",
                    "result": ns.get("result"),
                    "stdout": cap.getvalue(),
                }
            except Exception:
                res = {
                    "status": "error",
                    "message": traceback.format_exc(),
                    "stdout": cap.getvalue(),
                }
            finally:
                sys.stdout, sys.stderr = saved_out, saved_err

            with _result_lock:
                _result_map[tid] = res

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Per-connection handler (background thread)
# ---------------------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
    """Read request, dispatch to main thread, wait for result, send response."""
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
                (json.dumps({"status": "error",
                             "message": str(exc)}) + "\0").encode("utf-8")
            )
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Accept loop (background thread)
# ---------------------------------------------------------------------------

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
    """Start the MCP TCP server. Returns a status string."""
    global _server_socket, _task_queue, _running, _timer

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

        # Register QTimer for main-thread execution
        try:
            from PySide2.QtCore import QTimer  # FreeCAD 0.20+
        except ImportError:
            try:
                from PySide6.QtCore import QTimer  # FreeCAD 1.0+
            except ImportError:
                from PySide.QtCore import QTimer  # FreeCAD < 0.20

        _timer = QTimer()
        _timer.timeout.connect(_tick)
        _timer.start(_TICK_INTERVAL)

        msg = f"[FreeCAD MCP] Server ready on port {port}"
        print(msg)
        try:
            import FreeCAD
            FreeCAD.Console.PrintMessage(msg + "\n")
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
        return f"[FreeCAD MCP] Failed to start: {exc}"


def server_stop() -> str:
    """Stop the MCP TCP server."""
    global _server_socket, _running, _timer

    _running = False

    if _timer is not None:
        try:
            _timer.stop()
        except Exception:
            pass
        _timer = None

    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None

    msg = "[FreeCAD MCP] Server stopped"
    print(msg)
    return msg


def server_status() -> str:
    if _running and _server_socket:
        return f"Running (port {_DEFAULT_PORT})"
    return "Stopped"


# ---------------------------------------------------------------------------
# Auto-start when run as a macro
# ---------------------------------------------------------------------------

if __name__ == "__main__" or "FreeCAD" in sys.modules:
    try:
        server_start()
    except Exception as e:
        print(f"[FreeCAD MCP] Auto-start failed: {e}")
