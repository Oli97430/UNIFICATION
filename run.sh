#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[UNIFICATION] python3 not found. Install Python 3.10+ first."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[UNIFICATION] Creating virtual env..."
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip >/dev/null
    pip install -r requirements.txt
else
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

python main.py
