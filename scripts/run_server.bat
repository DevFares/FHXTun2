@echo off
cd /d "%~dp0\.."
title Asymmetric Python Proxy Server (Remote Server)
cls

echo ===============================================================
echo   Starting Asymmetric Python Proxy Server
echo ===============================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python launcher 'py' detected. Launching proxy server...
    echo.
    py server_main.py
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python executable 'python' detected. Launching proxy server...
    echo.
    python server_main.py
    goto end
)

echo.
echo [ERROR] Neither 'py' nor 'python' was found in system PATH.

:end
pause
