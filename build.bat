@echo off
setlocal
cd /d "%~dp0"

rem One-click build: produces a double-clickable single-file exe in dist\.
rem Prefer the project venv (it has selenium); fall back to whatever python is on PATH.

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" "%~dp0tools\build_exe.py" %*
if errorlevel 1 (
    echo.
    echo [FAILED] see the output above.
    pause
    exit /b 1
)

echo.
echo Done. Output is in the dist folder.
pause
