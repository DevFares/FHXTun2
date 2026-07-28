@echo off
cd /d "%~dp0\.."
title Disable Windows System Proxy
cls

echo ===============================================================
echo   DISABLING WINDOWS SYSTEM PROXY MODE
echo ===============================================================
echo.

:: Disable System Proxy
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f

echo.
echo [SUCCESS] Windows System Proxy has been DISABLED!
echo Your system is now back on direct internet connection mode.
echo.
pause
