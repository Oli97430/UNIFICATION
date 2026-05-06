@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [UNIFICATION] Python is not on PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [UNIFICATION] Creating virtual env...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

python main.py
endlocal
