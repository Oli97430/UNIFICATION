"""UNIFICATION — entry point.

Usage:
    python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when launched from anywhere.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
