#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt
pip show pyinstaller >/dev/null 2>&1 || pip install "pyinstaller>=6.0"

rm -rf build dist
pyinstaller --noconfirm Unification.spec

echo
echo "[UNIFICATION] Built dist/Unification"
