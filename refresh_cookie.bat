@echo off
cd /d "%~dp0"

rem 先尝试从 Firefox 直接读，读不到才会开浏览器扫码
set "NO_PROXY=localhost,127.0.0.1,::1"
set "no_proxy=localhost,127.0.0.1,::1"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" "%~dp0refresh_cookie.py"

echo.
echo ================================================
echo 按任意键关闭窗口
pause >nul
