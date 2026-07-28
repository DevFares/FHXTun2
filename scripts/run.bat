@echo off
cd /d "%~dp0\.."
title Asymmetric Python Proxy Client (Windows)
cls

echo ===============================================================
echo   Starting Asymmetric Python Proxy Client (Windows)
echo ===============================================================
echo.

:: Detect Python or Py launcher
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python launcher 'py' detected. Launching proxy...
    echo.
    py main.py
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Python executable 'python' detected. Launching proxy...
    echo.
    python main.py
    goto end
)

echo.
echo [ERROR] Neither 'py' nor 'python' was found in your system PATH!
echo Please install Python 3.10 or higher from https://www.python.org/
echo and ensure "Add Python to PATH" is checked during installation.
echo.

:end
pause
