"""Lightweight TCP ping for creative-app MCP addons.

Every addon uses the same JSON+\\0 protocol:  send {"type":"execute","code":"result = 'pong'"}
and expect {"status":"ok","result":"pong"} back.
"""
from __future__ import annotations

import json
import socket

# App registry — port assignments for each supported application
CREATIVE_APPS: dict[str, dict] = {
    "freecad":   {"name": "FreeCAD",   "port": 9877},
    "gimp":      {"name": "GIMP",      "port": 9878},
    "inkscape":  {"name": "Inkscape",  "port": 9879},
    "photoshop": {"name": "Photoshop", "port": 9880},
}


def ping_tcp_addon(host: str, port: int, timeout: float = 2.0) -> bool:
    """Send ``result='pong'`` to a TCP MCP addon, return *True* if it responds OK."""
    try:
        payload = json.dumps({"type": "execute", "code": "result = 'pong'"})
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload.encode("utf-8") + b"\x00")
            buf = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\x00" in chunk:
                    break
        raw = bytes(buf).rstrip(b"\x00").decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        return data.get("status") == "ok" and data.get("result") == "pong"
    except Exception:
        return False
