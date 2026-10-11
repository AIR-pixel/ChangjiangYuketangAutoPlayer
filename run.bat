@echo off
cd /d "%~dp0"

rem 本地 WebDriver 通信必须绕开系统代理，否则命令全部返回 unhandled request
set "NO_PROXY=localhost,127.0.0.1,::1"
set "no_proxy=localhost,127.0.0.1,::1"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" "%~dp0main.py"

echo.
echo ================================================
echo 程序已退出，按任意键关闭窗口
pause >nul
