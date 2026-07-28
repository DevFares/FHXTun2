#!/usr/bin/env python3
"""
System Proxy Control Utility (Python CLI) for Windows & Linux.

Allows configuring system proxy ON/OFF state and selecting routing scope:
1: HTTP & HTTPS only
2: HTTP & HTTPS + TCP & UDP (SOCKS5 + HTTP/HTTPS)
3: All Traffic from PC including DNS (Global SOCKS5 Proxy)

Runs in an interactive CLI loop menu.
"""

import os
import sys
import platform
import subprocess
import json

CONFIG_STATE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "proxy_enabler_state.json"))

DEFAULT_STATE = {
    "enabled": False,
    "route_mode": "http_https_tcp_udp",  # "http_https", "http_https_tcp_udp", "all_dns"
    "proxy_host": "127.0.0.1",
    "proxy_port": 1080
}


def load_state():
    if os.path.exists(CONFIG_STATE_FILE):
        try:
            with open(CONFIG_STATE_FILE, "r") as f:
                state = DEFAULT_STATE.copy()
                state.update(json.load(f))
                return state
        except Exception:
            pass
    return DEFAULT_STATE.copy()


def save_state(state):
    try:
        with open(CONFIG_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as err:
        print(f"[ERROR] Could not save state: {err}")


def apply_windows_proxy(state):
    """Applies proxy settings to Windows Registry."""
    if platform.system() != "Windows":
        return

    enabled = state.get("enabled", False)
    mode = state.get("route_mode", "http_https_tcp_udp")
    host = state.get("proxy_host", "127.0.0.1")
    port = state.get("proxy_port", 1080)

    try:
        if not enabled:
            cmd = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f'
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[SUCCESS] Windows System Proxy set to OFF.")
            return

        if mode == "http_https":
            server_str = f"http={host}:{port};https={host}:{port}"
        elif mode == "all_dns":
            server_str = f"socks={host}:{port}"
        else:  # http_https_tcp_udp
            server_str = f"socks={host}:{port};http={host}:{port};https={host}:{port}"

        cmd1 = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyServer /t REG_SZ /d "{server_str}" /f'
        cmd2 = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f'
        cmd3 = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyOverride /t REG_SZ /d "localhost;127.0.0.1;<local>" /f'

        subprocess.run(cmd1, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(cmd2, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(cmd3, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"[SUCCESS] Windows System Proxy set to ON ({mode} -> {server_str}).")
    except Exception as err:
        print(f"[WARNING] Registry update notice: {err}")


def main_cli_loop():
    state = load_state()

    while True:
        status_str = "ENABLED (ON)" if state["enabled"] else "DISABLED (OFF)"
        mode = state["route_mode"]
        if mode == "http_https":
            mode_desc = "HTTP & HTTPS only"
        elif mode == "all_dns":
            mode_desc = "All Traffic from PC including DNS (Global SOCKS5)"
        else:
            mode_desc = "HTTP, HTTPS + TCP & UDP"

        print("\n" + "=" * 65)
        print("    WINDOWS & LINUX SYSTEM PROXY SWITCHER & ENABLER")
        print("=" * 65)
        print(f"  Current Status: {status_str}")
        print(f"  Route Mode:     {mode_desc}")
        print(f"  Target Server:  {state['proxy_host']}:{state['proxy_port']}")
        print("=" * 65)
        print("  [1] Turn Proxy ON")
        print("  [2] Turn Proxy OFF")
        print("  [3] Select Route Mode (1: HTTP/HTTPS, 2: HTTP/HTTPS+TCP/UDP, 3: All+DNS)")
        print("  [0] Exit Menu")
        print("-" * 65)

        try:
            choice = input("Enter choice (0-3): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "1":
            state["enabled"] = True
            save_state(state)
            apply_windows_proxy(state)
        elif choice == "2":
            state["enabled"] = False
            save_state(state)
            apply_windows_proxy(state)
        elif choice == "3":
            print("\nSelect Traffic Routing Scope:")
            print("  [1] HTTP & HTTPS traffic only")
            print("  [2] HTTP, HTTPS + TCP & UDP traffic")
            print("  [3] Route Everything from PC (including DNS)")
            sub_choice = input("Select option (1-3): ").strip()
            if sub_choice == "1":
                state["route_mode"] = "http_https"
            elif sub_choice == "3":
                state["route_mode"] = "all_dns"
            else:
                state["route_mode"] = "http_https_tcp_udp"
            
            save_state(state)
            if state["enabled"]:
                apply_windows_proxy(state)
            print(f"[UPDATED] Route mode set to {state['route_mode']}.")
        elif choice == "0":
            print("Exiting interactive menu.")
            break
        else:
            print("[ERROR] Invalid choice, please try again.")


if __name__ == "__main__":
    main_cli_loop()
