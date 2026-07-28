@echo off
cd /d "%~dp0\.."
title Enable Windows System Proxy (127.0.0.1:1080)
cls

echo ===============================================================
echo   ENABLING WINDOWS SYSTEM PROXY MODE
echo   Target Local Proxy: 127.0.0.1:1080
echo ===============================================================
echo.

:: Set Proxy Server address (SOCKS5 and HTTP/HTTPS traffic to local proxy client)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "socks=127.0.0.1:1080;http=127.0.0.1:1080;https=127.0.0.1:1080" /f

:: Enable System Proxy
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f

:: Bypass proxy for local network connections
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /t REG_SZ /d "localhost;127.0.0.1;<local>" /f

echo.
echo [SUCCESS] Windows System Proxy has been ENABLED!
echo All applications using Windows System Proxy settings will now route traffic through 127.0.0.1:1080.
echo.
pause
