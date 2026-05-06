@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    pip install pyinstaller>=6.0
) else (
    call ".venv\Scripts\activate.bat"
    pip show pyinstaller >nul 2>nul || pip install pyinstaller>=6.0
)

if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

pyinstaller --noconfirm Unification.spec || goto :err

echo.
echo [UNIFICATION] Built dist\Unification.exe
exit /b 0

:err
echo.
echo [UNIFICATION] Build failed.
exit /b 1
