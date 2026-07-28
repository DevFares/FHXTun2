@echo off
cd /d "%~dp0\.."
title Asymmetric Proxy Web Config Server (Windows)
cls

echo ===============================================================
echo   Starting Flask Web Configuration Server
echo   Config File: config.json
echo   URL: http://127.0.0.1:5000
echo ===============================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python launcher 'py' detected. Launching web config server...
    echo.
    py web_config_server.py
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python executable 'python' detected. Launching web config server...
    echo.
    python web_config_server.py
    goto end
)

echo.
echo [ERROR] Neither 'py' nor 'python' was found in system PATH.

:end
pause
