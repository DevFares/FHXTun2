@echo off
cd /d "%~dp0\.."
title Asymmetric Proxy Unit Tests (Windows)
cls

echo ===============================================================
echo   Running Asymmetric Proxy Unit Tests
echo ===============================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -m unittest discover -s tests
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python -m unittest discover -s tests
    goto end
)

echo [ERROR] Neither 'py' nor 'python' was found in system PATH.

:end
pause
