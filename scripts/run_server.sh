#!/usr/bin/env bash
cd "$(dirname "$0")/.."
echo "==============================================================="
echo "   Starting Asymmetric Python Proxy Server (Remote Server)"
echo "==============================================================="
python3 server_main.py
