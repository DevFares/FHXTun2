#!/usr/bin/env bash
cd "$(dirname "$0")/.."
echo "==============================================================="
echo "   Starting Proxy Network Monitor & Configuration Server"
echo "   Config File: config.json"
echo "   URL: http://127.0.0.1:5000"
echo "==============================================================="
python3 proxy_monitor/app.py
