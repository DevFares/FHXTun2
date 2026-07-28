#!/usr/bin/env bash

# Script to clone FHXTun repository and launch the proxy server

REPO_URL="https://github.com/DevFares/FHXTun2.git"
TARGET_DIR="FHXTun"

echo "==============================================================="
echo "   FHXTun - Clone & Start Asymmetric Proxy Server"
echo "==============================================================="
apt install git  python3 -y
if [ -d "$TARGET_DIR" ]; then
    echo "[+] Directory '$TARGET_DIR' already exists."
    cd "$TARGET_DIR" || exit 1
    echo "[+] Fetching latest updates from repository..."
    git pull origin main || git pull || true
else
    echo "[+] Cloning repository from $REPO_URL..."
    git clone "$REPO_URL" "$TARGET_DIR"
    cd "$TARGET_DIR" || exit 1
fi

echo "---------------------------------------------------------------"
echo "[+] Navigated to: $(pwd)"
echo "[+] Launching Proxy Server (server_main.py)..."
echo "---------------------------------------------------------------"

if [ -f "server_main.py" ]; then
    python3 server_main.py
elif [ -f "run_server.sh" ]; then
    chmod +x run_server.sh
    ./run_server.sh
else
    echo "[!] Error: server_main.py or run_server.sh not found."
    exit 1
fi
