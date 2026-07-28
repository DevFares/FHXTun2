@echo off
cd /d "%~dp0\.."
title Windows System Proxy Switcher (1 = ON, 0 = OFF)
cls

echo ===============================================================
echo   Windows System Proxy Switcher
echo   Local Proxy Target: 127.0.0.1:1080
echo ===============================================================
echo.

:: Check if argument was passed via command line (e.g. proxy_switch.bat 1)
if "%1"=="1" goto enable
if "%1"=="0" goto disable

:menu
echo Enter [1] to ENABLE proxy mode (127.0.0.1:1080)
echo Enter [0] to DISABLE proxy mode (Direct connection)
echo.
set /p choice="Your Choice (1 or 0): "

if "%choice%"=="1" goto enable
if "%choice%"=="0" goto disable

echo.
echo [ERROR] Invalid selection! Please enter 1 to enable or 0 to disable.
echo.
goto menu

:enable
echo.
echo [INFO] Enabling Windows System Proxy (127.0.0.1:1080)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "socks=127.0.0.1:1080;http=127.0.0.1:1080;https=127.0.0.1:1080" /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /t REG_SZ /d "localhost;127.0.0.1;<local>" /f >nul
echo [SUCCESS] Proxy Mode is now ENABLED (127.0.0.1:1080).
echo.
pause
exit /b 0

:disable
echo.
echo [INFO] Disabling Windows System Proxy...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
echo [SUCCESS] Proxy Mode is now DISABLED (Direct Connection).
echo.
pause
exit /b 0
