#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Olivier Hoarau <Tarraw974@gmail.com>
"""
GIMP MCP Server Plugin
======================
Exposes a local TCP server (port 9878) so that UNIFICATION, Claude,
Cursor, or any MCP-compatible client can send Python-Fu code to execute
inside GIMP and receive the results in real-time.

Architecture (GIMP 3.x)
------------------------
GIMP 3 kills plugin sub-processes after each procedure call, so no
in-process TCP server can survive.  Instead:

1. Clicking **Filters > MCP Server Start** spawns a **standalone**
   Python process that listens on port 9878.
2. That standalone server forwards GIMP-specific code to the built-in
   **Script-Fu server** (port 10008) using ``python-fu-eval``, so the
   code still executes inside the running GIMP instance with full
   PDB access.
3. If the Script-Fu server is not running, the standalone server
   executes code locally (no GIMP modules available).

The user must also start the Script-Fu server:
  Filters > Script-Fu > Start Server…  (keep default port 10008)

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
3. Go to Filters -> Script-Fu -> Start Server  (keep port 10008)
4. Go to Filters -> MCP Server Start
"""

from __future__ import annotations

import json
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import traceback
from io import StringIO

# ---------------------------------------------------------------------------
# Addon metadata (read by UNIFICATION installer to detect version)
# ---------------------------------------------------------------------------

_addon_info = {
    "name": "GIMP MCP Server",
    "version": (1, 1, 0),
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PORT    = 9878
_SCRIPTFU_PORT   = 10008
_HOST            = "127.0.0.1"
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
# Script-Fu bridge — execute code inside GIMP via its Script-Fu TCP server
# ---------------------------------------------------------------------------

def _scriptfu_send(command: str, host: str = _HOST,
                   port: int = _SCRIPTFU_PORT,
                   timeout: float = 1.0) -> tuple[bool, str]:
    """Send a Script-Fu command to GIMP's Script-Fu server.

    Returns (ok, response_text).
    Protocol: 1-byte magic 'G' + 2-byte big-endian length + command.
    Response: 1-byte magic 'G' + 1-byte error code + 2-byte length + text.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            cmd_bytes = command.encode("utf-8")
            header = b"G" + struct.pack("!H", len(cmd_bytes))
            sock.sendall(header + cmd_bytes)

            # Read response header (4 bytes: G + error + 2-byte length)
            resp_hdr = b""
            while len(resp_hdr) < 4:
                chunk = sock.recv(4 - len(resp_hdr))
                if not chunk:
                    break
                resp_hdr += chunk

            if len(resp_hdr) < 4:
                return False, "Script-Fu: incomplete response header"

            _magic, err_code, resp_len = struct.unpack("!cBH", resp_hdr)
            # Read response body
            body = b""
            while len(body) < resp_len:
                chunk = sock.recv(resp_len - len(body))
                if not chunk:
                    break
                body += chunk

            text = body.decode("utf-8", errors="replace")
            return (err_code == 0), text
    except (ConnectionRefusedError, ConnectionResetError,
            TimeoutError, OSError):
        return False, "__CONNECTION_FAILED__"
    except Exception as exc:
        return False, str(exc)


def _execute_via_scriptfu(code: str) -> dict | None:
    """Try to execute Python code inside GIMP via Script-Fu bridge.

    Wraps the code in a python-fu-eval call and sends it to GIMP's
    Script-Fu server.  Returns None if the Script-Fu server is not
    reachable (caller should fall back to local execution).
    """
    # Escape the Python code for embedding in a Script-Fu string literal.
    escaped = code.replace("\\", "\\\\").replace('"', '\\"')
    sf_cmd = f'(python-fu-eval 1 "{escaped}")'

    ok, text = _scriptfu_send(sf_cmd)

    if text == "__CONNECTION_FAILED__":
        return None  # Script-Fu server not running — fall back

    if ok:
        return {
            "status": "ok",
            "result": text.strip() if text.strip() else None,
            "stdout": text,
        }
    else:
        return {
            "status": "error",
            "message": f"Script-Fu bridge error: {text}",
            "stdout": "",
        }


# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------

_has_gimp_modules = False  # set True if running inside GIMP process


_GIMP_KEYWORDS = {"gimp", "pdb", "gimpfu", "gimpenums", "Gimp", "GLib", "Gio"}


def _code_needs_gimp(code: str) -> bool:
    """Heuristic: does *code* reference GIMP-specific names?"""
    for kw in _GIMP_KEYWORDS:
        if kw in code:
            return True
    return False


def _execute_code(code: str) -> dict:
    """Execute Python code, using GIMP modules if available.

    Resolution order:
    1. Direct execution with injected GIMP modules (inside GIMP process).
    2. Script-Fu bridge → python-fu-eval (standalone server → GIMP).
    3. Local execution without GIMP modules (generic Python).
       If the code references GIMP modules, returns a clear error.
    """
    global _has_gimp_modules

    # --- Path 1: inside GIMP (GIMP 2.x in-process server) ----------------
    if _has_gimp_modules:
        return _execute_code_local(code, inject_gimp=True)

    # --- Path 2: Script-Fu bridge (standalone → GIMP 3.x) ----------------
    result = _execute_via_scriptfu(code)
    if result is not None:
        return result

    # --- Path 3: local execution (no GIMP modules) -----------------------
    result = _execute_code_local(code, inject_gimp=False)

    # If it failed because of missing GIMP modules, give a clear message
    if (result.get("status") == "error"
            and _code_needs_gimp(code)
            and "ModuleNotFoundError" in result.get("message", "")):
        result["message"] = (
            "[GIMP MCP] GIMP modules (gimp, pdb, gimpfu...) are not "
            "available in standalone mode.\n"
            "GIMP 3.x kills plugin sub-processes, so the MCP server "
            "runs as a separate process without GIMP context.\n\n"
            "- Use generic Python code (no gimp imports) for now.\n"
            "- GIMP-specific control will be added in a future version "
            "via a D-Bus bridge.\n\n"
            "Original error: " + result["message"].split("\n")[-2]
        )
    return result


def _execute_code_local(code: str, *, inject_gimp: bool = True) -> dict:
    """Execute Python code locally with optional GIMP module injection."""
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = cap = StringIO()
    try:
        ns = {"result": None}

        if inject_gimp:
            # Inject GIMP modules into namespace
            for mod_name, import_code in [
                ("gimp",     "import gimp"),
                ("pdb",      "from gimp import pdb"),
                ("gimpfu",   "import gimpfu"),
                ("gimpenums","import gimpenums"),
            ]:
                try:
                    exec(import_code, ns)
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

def _is_socket_alive() -> bool:
    """Check if the server socket is still bound and usable."""
    if not _server_socket:
        return False
    try:
        _server_socket.getsockname()
        return True
    except Exception:
        return False


def server_start(port: int = _DEFAULT_PORT, *, standalone: bool = False) -> str:
    global _server_socket, _task_queue, _running

    if _running and _server_socket:
        if _is_socket_alive():
            return f"Already running on port {port}"
        # Socket died — reset and restart
        _running = False
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None

    _task_queue = queue.Queue()

    try:
        _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _server_socket.bind((_HOST, port))
        _server_socket.listen(5)
        threading.Thread(target=_accept_loop, args=(_server_socket,), daemon=True).start()
        _running = True

        # Register task-queue ticker.
        # In standalone mode there is no GLib main loop, so always use a
        # background thread.  Inside GIMP we prefer GLib.timeout_add.
        def _start_bg_tick():
            def _bg_tick():
                import time
                while _running:
                    _tick()
                    time.sleep(_TICK_INTERVAL / 1000.0)
            threading.Thread(target=_bg_tick, daemon=True).start()

        if standalone:
            _start_bg_tick()
        else:
            try:
                from gi.repository import GLib
                GLib.timeout_add(_TICK_INTERVAL, _tick)
            except ImportError:
                try:
                    import gobject
                    gobject.timeout_add(_TICK_INTERVAL, _tick)
                except ImportError:
                    _start_bg_tick()

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
# Standalone mode — must be checked BEFORE GIMP registration blocks,
# otherwise the GIMP 3 block may call Gimp.main() and crash.
# ---------------------------------------------------------------------------

# Detect standalone mode: explicit --standalone flag (set by the GIMP 3
# plugin spawner) or manual launch without GIMP's "-gimp" argv.
_standalone_requested = "--standalone" in sys.argv
_is_gimp_subprocess = any(a == "-gimp" for a in sys.argv)

if _standalone_requested or (__name__ == "__main__" and not _is_gimp_subprocess):
    print("[GIMP MCP] Running in standalone mode")
    # Check if Script-Fu bridge is available
    ok, _ = _scriptfu_send("(gimp-version)")
    if ok:
        print("[GIMP MCP] Script-Fu bridge connected → full GIMP access via port 10008")
    else:
        print("[GIMP MCP] Script-Fu bridge unavailable — start it in GIMP:")
        print("           Filters > Script-Fu > Start Server  (port 10008)")
    server_start(standalone=True)
    try:
        threading.Event().wait()  # block forever
    except KeyboardInterrupt:
        server_stop()
    sys.exit(0)


# ---------------------------------------------------------------------------
# GIMP 2.x Plugin Registration
# ---------------------------------------------------------------------------

try:
    from gimpfu import register, main

    _has_gimp_modules = True  # running inside GIMP 2

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
#
# Strategy: GIMP 3 kills plugin sub-processes after each procedure call,
# so we spawn a *detached standalone* Python process that survives.  That
# standalone process bridges to GIMP's Script-Fu server (port 10008) for
# code that needs PDB / gimp module access.
# ---------------------------------------------------------------------------

try:
    import gi
    gi.require_version("Gimp", "3.0")
    from gi.repository import Gimp, GObject, GLib

    # Sensitivity: always available, even without an image open.
    _SENSITIVITY = (
        Gimp.ProcedureSensitivityMask.DRAWABLE
        | Gimp.ProcedureSensitivityMask.DRAWABLES
        | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
        | Gimp.ProcedureSensitivityMask.NO_IMAGE
    )

    def _find_python() -> str:
        """Return path to a usable Python interpreter."""
        # Prefer GIMP's bundled Python (has gi bindings)
        gimp_dir = os.path.dirname(os.path.dirname(sys.executable))
        candidates = [
            os.path.join(gimp_dir, "bin", "python.exe"),
            os.path.join(gimp_dir, "bin", "python3.exe"),
            sys.executable,
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return sys.executable

    def _spawn_standalone() -> str:
        """Spawn a detached standalone MCP server process."""
        import tempfile

        script_path = os.path.abspath(__file__)
        python_exe = _find_python()

        # Check if already running on port 9878
        try:
            with socket.create_connection((_HOST, _DEFAULT_PORT), timeout=1.0):
                return f"[GIMP MCP] Already running on port {_DEFAULT_PORT}"
        except Exception:
            pass

        # Kill any leftover process on the port
        # (not strictly needed — bind will fail if port is in use)

        # Spawn detached process
        if sys.platform == "win32":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            proc = subprocess.Popen(
                [python_exe, script_path, "--standalone"],
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                [python_exe, script_path, "--standalone"],
                start_new_session=True,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Wait briefly for it to come up
        import time
        for _ in range(20):
            time.sleep(0.25)
            try:
                with socket.create_connection((_HOST, _DEFAULT_PORT), timeout=0.5):
                    return (
                        f"[GIMP MCP] Standalone server started (PID {proc.pid}) "
                        f"on port {_DEFAULT_PORT}"
                    )
            except Exception:
                continue

        return (
            f"[GIMP MCP] Server process spawned (PID {proc.pid}) but port "
            f"{_DEFAULT_PORT} not yet responding"
        )

    class MCPServerPlugin(Gimp.PlugIn):

        def do_query_procedures(self):
            return ["mcp-server-start", "mcp-server-stop"]

        def do_set_i18n(self, name):
            return False

        def do_create_procedure(self, name):
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN,
                self._start_run if name == "mcp-server-start" else self._stop_run,
                None,
            )
            procedure.set_image_types("*")
            procedure.set_sensitivity_mask(_SENSITIVITY)
            label = "MCP Server Start" if name == "mcp-server-start" else "MCP Server Stop"
            procedure.set_menu_label(label)
            procedure.add_menu_path("<Image>/Filters")
            procedure.set_documentation(label, label, name)
            procedure.set_attribution("Olivier Hoarau", "GPL-3.0", "2026")
            return procedure

        def _start_run(self, procedure, run_mode, image, drawables, config, run_data):
            import tempfile
            dbg = os.path.join(tempfile.gettempdir(), "gimp_mcp_debug.txt")
            try:
                msg = _spawn_standalone()
                with open(dbg, "w") as f:
                    f.write(f"OK: {msg}\n")
                Gimp.message(str(msg))
            except Exception as exc:
                with open(dbg, "w") as f:
                    f.write(f"ERROR: {exc}\n{traceback.format_exc()}")
                Gimp.message(f"[MCP] start error: {exc}")
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        def _stop_run(self, procedure, run_mode, image, drawables, config, run_data):
            try:
                # Send shutdown signal to standalone server
                try:
                    with socket.create_connection((_HOST, _DEFAULT_PORT), timeout=2.0) as s:
                        s.sendall(
                            (json.dumps({"type": "execute",
                                         "code": "import os; os._exit(0)"})
                             + "\0").encode("utf-8")
                        )
                except Exception:
                    pass
                Gimp.message("[GIMP MCP] Server stopped")
            except Exception as exc:
                Gimp.message(f"[MCP] stop error: {exc}")
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    Gimp.main(MCPServerPlugin.__gtype__, sys.argv)

except (ImportError, ValueError):
    # Not running inside GIMP 3 either
    pass

# (standalone mode is handled before GIMP registration blocks above)
