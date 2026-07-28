#!/usr/bin/env python3
"""
Flask / Standard HTTP Web Application for Proxy Enabler & System Traffic Controller.

Provides an interactive Web Dashboard and REST API to:
- Turn System Proxy ON / OFF
- Choose traffic routing mode:
  1) HTTP & HTTPS only
  2) HTTP & HTTPS + TCP & UDP
  3) All Traffic from PC including DNS
"""

import os
import sys
import json
import logging

try:
    from flask import Flask, request, jsonify, render_template_string
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

# Import local proxy state controller
sys.path.insert(0, os.path.dirname(__file__))
from toggle_proxy import load_state, save_state, apply_windows_proxy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("proxy_enabler_app")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>System Proxy Enabler & Routing Controller</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-dim: #94a3b8;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --success: #10b981;
      --cyan: #06b6d4;
      --danger: #f43f5e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 32px 16px;
      line-height: 1.5;
    }
    .container { max-width: 700px; margin: 0 auto; }
    header {
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    h1 { font-size: 20px; font-weight: 700; color: #fff; }
    .subtitle { font-size: 13px; color: var(--text-dim); margin-top: 4px; }
    .badge {
      background: rgba(6, 182, 212, 0.1);
      color: var(--cyan);
      border: 1px solid rgba(6, 182, 212, 0.3);
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-family: monospace;
    }
    .badge.on { background: rgba(16, 185, 129, 0.15); color: var(--success); border-color: rgba(16, 185, 129, 0.4); }
    .badge.off { background: rgba(244, 63, 94, 0.15); color: var(--danger); border-color: rgba(244, 63, 94, 0.4); }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 20px;
    }
    .card-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 16px;
      color: var(--cyan);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .status-toggle-box {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0f172a;
      border: 1px solid var(--border);
      padding: 16px 20px;
      border-radius: 10px;
      margin-bottom: 20px;
    }
    .switch-btn {
      padding: 10px 24px;
      font-size: 14px;
      font-weight: 700;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      transition: all 0.2s;
    }
    .switch-btn.enable { background: var(--success); color: #022c22; }
    .switch-btn.enable:hover { background: #34d399; }
    .switch-btn.disable { background: var(--danger); color: #450a0a; }
    .switch-btn.disable:hover { background: #fb7185; }

    .route-option {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 14px;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 10px;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .route-option:hover { border-color: var(--cyan); }
    .route-option input[type="radio"] { margin-top: 4px; accent-color: var(--cyan); width: 18px; height: 18px; }
    .route-info { display: flex; flex-direction: column; gap: 2px; }
    .route-title { font-size: 14px; font-weight: 600; color: #fff; }
    .route-desc { font-size: 12px; color: var(--text-dim); }

    .actions { display: flex; justify-content: flex-end; margin-top: 20px; }
    button.primary {
      background: var(--accent);
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
    }
    button.primary:hover { background: var(--accent-hover); }

    .alert {
      padding: 12px 16px;
      border-radius: 8px;
      margin-top: 16px;
      font-size: 13px;
      display: none;
    }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #34d399; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>System Proxy Enabler</h1>
        <div class="subtitle">Windows & System Traffic Routing Controller</div>
      </div>
      <div id="statusBadge" class="badge">Checking...</div>
    </header>

    <div class="card">
      <div class="card-title">System Proxy Status</div>
      <div class="status-toggle-box">
        <div>
          <div id="statusText" style="font-size: 16px; font-weight: 700; color: #fff;">-</div>
          <div id="targetText" style="font-size: 12px; color: var(--text-dim);">Target: 127.0.0.1:1080</div>
        </div>
        <button id="toggleBtn" class="switch-btn enable" onclick="toggleProxy()">Toggle Proxy</button>
      </div>

      <div class="card-title" style="margin-top: 24px;">Traffic Routing Options</div>
      <form id="routeForm" onsubmit="applyRoute(event)">
        <label class="route-option">
          <input type="radio" name="route_mode" value="http_https" id="rm_http_https">
          <div class="route-info">
            <span class="route-title">HTTP & HTTPS Only</span>
            <span class="route-desc">Routes standard web browser HTTP and HTTPS traffic through proxy.</span>
          </div>
        </label>

        <label class="route-option">
          <input type="radio" name="route_mode" value="http_https_tcp_udp" id="rm_http_https_tcp_udp">
          <div class="route-info">
            <span class="route-title">HTTP, HTTPS + TCP & UDP (Default SOCKS5)</span>
            <span class="route-desc">Routes browser traffic plus application TCP and UDP sockets over SOCKS5 proxy (127.0.0.1:1080).</span>
          </div>
        </label>

        <label class="route-option">
          <input type="radio" name="route_mode" value="all_dns" id="rm_all_dns">
          <div class="route-info">
            <span class="route-title">Route Everything from PC (including DNS)</span>
            <span class="route-desc">Redirects all PC application traffic and remote DNS queries directly through SOCKS5 proxy.</span>
          </div>
        </label>

        <div class="actions">
          <button type="submit" class="primary">Apply Selected Routing Option</button>
        </div>
      </form>

      <div id="alertBox" class="alert alert-success"></div>
    </div>
  </div>

  <script>
    let currentState = {};

    async function loadStatus() {
      try {
        const res = await fetch('/api/proxy-enabler/status');
        if (res.ok) {
          currentState = await res.json();
          renderState();
        }
      } catch (err) {
        console.error('Failed to load status:', err);
      }
    }

    function renderState() {
      const badge = document.getElementById('statusBadge');
      const text = document.getElementById('statusText');
      const btn = document.getElementById('toggleBtn');

      if (currentState.enabled) {
        badge.className = 'badge on';
        badge.textContent = 'Proxy ENABLED (ON)';
        text.textContent = 'System Proxy is ACTIVE';
        btn.className = 'switch-btn disable';
        btn.textContent = 'Turn Proxy OFF';
      } else {
        badge.className = 'badge off';
        badge.textContent = 'Proxy DISABLED (OFF)';
        text.textContent = 'System Proxy is INACTIVE (Direct)';
        btn.className = 'switch-btn enable';
        btn.textContent = 'Turn Proxy ON';
      }

      const mode = currentState.route_mode || 'http_https_tcp_udp';
      const rad = document.getElementById('rm_' + mode);
      if (rad) rad.checked = true;
    }

    async function toggleProxy() {
      try {
        const res = await fetch('/api/proxy-enabler/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: !currentState.enabled })
        });
        const data = await res.json();
        if (data.success) {
          currentState = data.state;
          renderState();
          showAlert('Proxy status successfully updated!');
        }
      } catch (err) {
        alert('Error toggling proxy: ' + err.message);
      }
    }

    async function applyRoute(e) {
      e.preventDefault();
      const selected = document.querySelector('input[name="route_mode"]:checked').value;
      try {
        const res = await fetch('/api/proxy-enabler/route-option', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ route_mode: selected })
        });
        const data = await res.json();
        if (data.success) {
          currentState = data.state;
          renderState();
          showAlert('Traffic routing mode updated to: ' + selected);
        }
      } catch (err) {
        alert('Error updating route mode: ' + err.message);
      }
    }

    function showAlert(msg) {
      const el = document.getElementById('alertBox');
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 3000);
    }

    loadStatus();
  </script>
</body>
</html>
"""

if HAS_FLASK:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route("/api/proxy-enabler/status", methods=["GET"])
    def get_status():
        return jsonify(load_state())

    @app.route("/api/proxy-enabler/toggle", methods=["POST"])
    def toggle():
        data = request.get_json(force=True) or {}
        state = load_state()
        state["enabled"] = bool(data.get("enabled", not state["enabled"]))
        save_state(state)
        apply_windows_proxy(state)
        return jsonify({"success": True, "state": state})

    @app.route("/api/proxy-enabler/route-option", methods=["POST"])
    def set_route_option():
        data = request.get_json(force=True) or {}
        mode = data.get("route_mode", "http_https_tcp_udp")
        state = load_state()
        state["route_mode"] = mode
        save_state(state)
        if state["enabled"]:
            apply_windows_proxy(state)
        return jsonify({"success": True, "state": state})

    def run_enabler_server(port=5001):
        print("===============================================================")
        print(f"   Starting Proxy Enabler Flask Server on http://127.0.0.1:{port}")
        print("===============================================================")
        app.run(host="0.0.0.0", port=port, debug=False)
else:
    class ProxyEnablerHTTPHandler(BaseHTTPRequestHandler):
        def _set_headers(self, status=200, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_OPTIONS(self):
            self._set_headers(200)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                self._set_headers(200, "text/html; charset=utf-8")
                self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            elif parsed.path in ["/api/proxy-enabler/status", "/api/status"]:
                self._set_headers(200)
                self.wfile.write(json.dumps(load_state()).encode("utf-8"))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            body_str = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body_str)
            except Exception:
                data = {}

            if parsed.path == "/api/proxy-enabler/toggle":
                state = load_state()
                state["enabled"] = bool(data.get("enabled", not state["enabled"]))
                save_state(state)
                apply_windows_proxy(state)
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True, "state": state}).encode("utf-8"))
            elif parsed.path == "/api/proxy-enabler/route-option":
                mode = data.get("route_mode", "http_https_tcp_udp")
                state = load_state()
                state["route_mode"] = mode
                save_state(state)
                if state["enabled"]:
                    apply_windows_proxy(state)
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True, "state": state}).encode("utf-8"))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def run_enabler_server(port=5001):
        print("===============================================================")
        print(f"   Starting Proxy Enabler Standard HTTP Server on http://127.0.0.1:{port}")
        print("===============================================================")
        server = HTTPServer(("0.0.0.0", port), ProxyEnablerHTTPHandler)
        server.serve_forever()

if __name__ == "__main__":
    port = 5001
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_enabler_server(port)
