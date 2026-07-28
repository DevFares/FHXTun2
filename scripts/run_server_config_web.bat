@echo off
cd /d "%~dp0\.."
title Asymmetric Server Proxy Web Config Server (Windows)
echo ===============================================================
echo    Starting Flask Server Proxy Web Configuration Server
echo    Config File: server_config.json
echo    URL: http://127.0.0.1:5001
echo ===============================================================
python -m asymmetric_server.web_config.web_config_server
pause
