#!/usr/bin/env python3
"""
Flask / Standard HTTP Network Monitor & Configuration Web Application for Asymmetric Proxy Client.

Provides a full browser dashboard and REST API to:
1. Live Monitor Proxy Network Packets:
   - Live Raw Received Packets (Socket level)
   - Live Unpacked Unobfuscated Payload Data
   - MTCM Port Range Connection & Disconnection Events
2. Manage & Toggle Client Parameters (config.json):
   - Local & Remote Endpoints
   - MTCM Port Ranges & Enable/Disable status
   - Packet Logging Switches (write_received_packets_full & write_received_packets_data)
   - HTTP Response Obfuscation & Template Settings
   - Buffer & Socket Timeouts
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

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from asymmetric_proxy.config import (
    CONFIG_FILE_PATH,
    load_config_file,
    save_config_file,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("proxy_monitor_app")

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Asymmetric Proxy Client Network Monitor & Configuration</title>
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
      --amber: #f59e0b;
      --rose: #f43f5e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px 16px;
      line-height: 1.5;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
      margin-bottom: 20px;
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

    .nav-tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }
    .tab-btn {
      background: transparent;
      color: var(--text-dim);
      border: 1px solid transparent;
      padding: 8px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
    }
    .tab-btn.active {
      background: var(--card-bg);
      color: #fff;
      border-color: var(--border);
      color: var(--cyan);
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .card-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 14px;
      color: var(--cyan);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .log-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .log-box {
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .log-header {
      background: #0f172a;
      padding: 10px 14px;
      font-weight: 600;
      font-size: 12px;
      color: var(--text-dim);
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    pre.log-viewer {
      padding: 12px;
      font-family: monospace;
      font-size: 11px;
      height: 320px;
      overflow-y: auto;
      white-space: pre-wrap;
      color: #cbd5e1;
      background: #020617;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    label { font-size: 12px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; font-family: monospace; }
    input, select, textarea {
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-family: monospace;
      outline: none;
    }
    input:focus, select:focus, textarea:focus { border-color: var(--cyan); }
    .help-text { font-size: 11px; color: #64748b; }

    .actions { display: flex; gap: 12px; justify-content: flex-end; margin-top: 20px; }
    button {
      background: var(--accent);
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: var(--accent-hover); }
    button.secondary { background: #334155; }
    button.secondary:hover { background: #475569; }

    .alert {
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 16px;
      font-size: 13px;
      display: none;
    }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #34d399; }
    
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .status-pill { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; }
    .pill-active { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .pill-inactive { background: rgba(244, 63, 94, 0.2); color: #fca5a5; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Asymmetric Proxy Network Monitor</h1>
        <div class="subtitle">Live Received Stream Inspection & Configuration Editor</div>
      </div>
      <div class="badge">Network Monitor Server</div>
    </header>

    <div id="alertBox" class="alert"></div>

    <div class="nav-tabs">
      <button class="tab-btn active" id="tabBtnMonitor" onclick="switchTab('monitor')">Live Network Monitor</button>
      <button class="tab-btn" id="tabBtnConfig" onclick="switchTab('config')">Proxy Settings (config.json)</button>
    </div>

    <!-- TAB 1: LIVE MONITORING -->
    <div id="viewMonitor" class="tab-content active">
      <div class="card">
        <div class="card-title">
          <span>Port Range Control & Logging Toggles</span>
          <div style="display: flex; gap: 8px;">
            <button class="secondary" style="padding: 4px 10px; font-size: 11px;" onclick="clearLogFiles()">Clear Log Files</button>
          </div>
        </div>
        <div class="form-grid">
          <div class="form-group">
            <label>MTCM Return Port Start</label>
            <input type="number" id="quick_port_start" value="2525">
          </div>
          <div class="form-group">
            <label>MTCM Return Port End</label>
            <input type="number" id="quick_port_end" value="2530">
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <div style="display: flex; gap: 20px; align-items: center; margin-top: 6px;">
              <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: #fff; font-size: 13px;">
                <input type="checkbox" id="quick_write_full" style="width: 16px; height: 16px;" onchange="toggleQuickLoggers()">
                Enable Raw Socket Packets Logging (received_packets_full.txt)
              </label>
              <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: #fff; font-size: 13px;">
                <input type="checkbox" id="quick_write_data" style="width: 16px; height: 16px;" onchange="toggleQuickLoggers()">
                Enable Extracted Unobfuscated Payload Data Logging (received_packets_data.txt)
              </label>
            </div>
          </div>
        </div>
        <div style="margin-top: 12px; display: flex; justify-content: flex-end;">
          <button onclick="applyPortRange()">Update Port Range & Apply</button>
        </div>
      </div>

      <div class="log-grid">
        <!-- Panel 1: Raw Received Packets -->
        <div class="log-box">
          <div class="log-header">
            <span style="color: var(--cyan);">1. Received Packets (Live Raw Socket Chunks)</span>
            <span id="badgeFullLog" class="status-pill pill-inactive">Logging OFF</span>
          </div>
          <pre id="viewerFullLog" class="log-viewer">Loading raw socket packet logs...</pre>
        </div>

        <!-- Panel 2: Unpacked Unobfuscated Payload Data -->
        <div class="log-box">
          <div class="log-header">
            <span style="color: var(--success);">2. Unpacked Unobfuscated Payload Data (Live)</span>
            <span id="badgeDataLog" class="status-pill pill-inactive">Logging OFF</span>
          </div>
          <pre id="viewerDataLog" class="log-viewer">Loading unpacked payload logs...</pre>
        </div>
      </div>

      <!-- Panel 3: Connection Events -->
      <div class="log-box" style="margin-bottom: 24px;">
        <div class="log-header">
          <span style="color: var(--amber);">3. MTCM Client Port Range Connection Open & Socket Close Events</span>
          <span class="status-pill pill-active">Auto-Logged</span>
        </div>
        <pre id="viewerEventsLog" class="log-viewer" style="height: 180px;">Loading MTCM connection events...</pre>
      </div>
    </div>

    <!-- TAB 2: CONFIGURATION EDITOR -->
    <div id="viewConfig" class="tab-content">
      <form id="configForm" onsubmit="saveConfig(event)">
        <div class="card">
          <div class="card-title">Local & Remote Endpoints</div>
          <div class="form-grid">
            <div class="form-group">
              <label>Local Ingress Host</label>
              <input type="text" id="local_host" name="local_host" required>
            </div>
            <div class="form-group">
              <label>Local Ingress Port</label>
              <input type="number" id="local_port" name="local_port" required>
            </div>
            <div class="form-group">
              <label>Remote Proxy Host</label>
              <input type="text" id="remote_proxy_host" name="remote_proxy_host" required>
            </div>
            <div class="form-group">
              <label>Remote UDP Port (UCMC)</label>
              <input type="number" id="remote_udp_port" name="remote_udp_port" required>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Client MultiTCP Connection Pool (MTCM)</div>
          <div class="form-grid">
            <div class="form-group">
              <label>MTCM Port Start Range</label>
              <input type="number" id="mtcm_port_start" name="mtcm_port_start" required>
            </div>
            <div class="form-group">
              <label>MTCM Port End Range</label>
              <input type="number" id="mtcm_port_end" name="mtcm_port_end" required>
            </div>
            <div class="form-group">
              <label>Max MTCM Active Sockets</label>
              <input type="number" id="max_mtcm_connections" name="max_mtcm_connections" required>
            </div>
            <div class="form-group">
              <label>Socket Idle Timeout (Seconds)</label>
              <input type="number" id="socket_timeout" name="socket_timeout" required>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">HTTP Response Obfuscation & Packet Logging Options</div>
          <div class="form-grid">
            <div class="form-group" style="grid-column: 1 / -1;">
              <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: #fff;">
                <input type="checkbox" id="http_obfuscation_enabled" name="http_obfuscation_enabled" style="width: 18px; height: 18px; accent-color: var(--cyan);">
                Enable HTTP Response Obfuscation
              </label>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: #fff;">
                <input type="checkbox" id="write_received_packets_full" name="write_received_packets_full" style="width: 18px; height: 18px; accent-color: var(--cyan);">
                Write Received Packets Full Format (received_packets_full.txt)
              </label>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: #fff;">
                <input type="checkbox" id="write_received_packets_data" name="write_received_packets_data" style="width: 18px; height: 18px; accent-color: var(--cyan);">
                Write Received Packets Only Data (received_packets_data.txt)
              </label>
            </div>
          </div>
        </div>

        <div class="actions">
          <button type="button" class="secondary" onclick="loadConfig()">Reset to Saved File</button>
          <button type="submit">Save Configuration File</button>
        </div>
      </form>
    </div>
  </div>

  <script>
    let currentConfig = {};

    function switchTab(tabName) {
      if (tabName === 'monitor') {
        document.getElementById('viewMonitor').classList.add('active');
        document.getElementById('viewConfig').classList.remove('active');
        document.getElementById('tabBtnMonitor').classList.add('active');
        document.getElementById('tabBtnConfig').classList.remove('active');
      } else {
        document.getElementById('viewMonitor').classList.remove('active');
        document.getElementById('viewConfig').classList.add('active');
        document.getElementById('tabBtnMonitor').classList.remove('active');
        document.getElementById('tabBtnConfig').classList.add('active');
        loadConfig();
      }
    }

    async function loadConfig() {
      try {
        const res = await fetch('/api/config');
        if (res.ok) {
          currentConfig = await res.json();
          populateConfigForm();
        }
      } catch (err) {
        console.error('Error loading config:', err);
      }
    }

    function populateConfigForm() {
      for (const [key, val] of Object.entries(currentConfig)) {
        const el = document.getElementById(key);
        if (el) {
          if (el.type === 'checkbox') {
            el.checked = !!val;
          } else {
            el.value = val;
          }
        }
      }

      document.getElementById('quick_port_start').value = currentConfig.mtcm_port_start || 2525;
      document.getElementById('quick_port_end').value = currentConfig.mtcm_port_end || 2530;
      document.getElementById('quick_write_full').checked = !!currentConfig.write_received_packets_full;
      document.getElementById('quick_write_data').checked = !!currentConfig.write_received_packets_data;

      updateBadges();
    }

    function updateBadges() {
      const fullBadge = document.getElementById('badgeFullLog');
      const dataBadge = document.getElementById('badgeDataLog');

      if (currentConfig.write_received_packets_full) {
        fullBadge.className = 'status-pill pill-active';
        fullBadge.textContent = 'Logging ON';
      } else {
        fullBadge.className = 'status-pill pill-inactive';
        fullBadge.textContent = 'Logging OFF';
      }

      if (currentConfig.write_received_packets_data) {
        dataBadge.className = 'status-pill pill-active';
        dataBadge.textContent = 'Logging ON';
      } else {
        dataBadge.className = 'status-pill pill-inactive';
        dataBadge.textContent = 'Logging OFF';
      }
    }

    async function toggleQuickLoggers() {
      const fullVal = document.getElementById('quick_write_full').checked;
      const dataVal = document.getElementById('quick_write_data').checked;
      
      currentConfig.write_received_packets_full = fullVal;
      currentConfig.write_received_packets_data = dataVal;

      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentConfig)
      });
      updateBadges();
    }

    async function applyPortRange() {
      const pStart = parseInt(document.getElementById('quick_port_start').value, 10);
      const pEnd = parseInt(document.getElementById('quick_port_end').value, 10);

      try {
        const res = await fetch('/api/proxy/toggle-ports', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mtcm_port_start: pStart, mtcm_port_end: pEnd })
        });
        const data = await res.json();
        if (data.success) {
          showAlert('Port range updated to ' + pStart + ' - ' + pEnd);
          loadConfig();
        }
      } catch (err) {
        alert('Failed to update ports: ' + err.message);
      }
    }

    async function saveConfig(e) {
      e.preventDefault();
      const form = document.getElementById('configForm');
      const formData = new FormData(form);
      const payload = {};

      formData.forEach((value, key) => {
        if (['local_port', 'remote_udp_port', 'mtcm_port_start', 'mtcm_port_end', 'max_mtcm_connections', 'socket_timeout', 'socket_buffer_size', 'chunk_read_size'].includes(key)) {
          payload[key] = parseInt(value, 10);
        } else if (['http_obfuscation_enabled', 'write_received_packets_full', 'write_received_packets_data'].includes(key)) {
          payload[key] = true;
        } else {
          payload[key] = value;
        }
      });

      ['http_obfuscation_enabled', 'write_received_packets_full', 'write_received_packets_data'].forEach(k => {
        if (!formData.has(k)) payload[k] = false;
      });

      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
          showAlert('Saved configuration successfully!');
          loadConfig();
        } else {
          alert('Error: ' + result.error);
        }
      } catch (err) {
        alert('Failed to save config: ' + err.message);
      }
    }

    async function fetchLogs() {
      try {
        const [resFull, resData, resEvts] = await Promise.all([
          fetch('/api/logs/full'),
          fetch('/api/logs/data'),
          fetch('/api/logs/events')
        ]);

        if (resFull.ok) {
          const d = await resFull.json();
          const el = document.getElementById('viewerFullLog');
          el.textContent = d.content || '(No raw packet logs recorded yet)';
          el.scrollTop = el.scrollHeight;
        }
        if (resData.ok) {
          const d = await resData.json();
          const el = document.getElementById('viewerDataLog');
          el.textContent = d.content || '(No unpacked payload data logs recorded yet)';
          el.scrollTop = el.scrollHeight;
        }
        if (resEvts.ok) {
          const d = await resEvts.json();
          const el = document.getElementById('viewerEventsLog');
          el.textContent = d.content || '(No MTCM connection events recorded yet)';
          el.scrollTop = el.scrollHeight;
        }
      } catch (err) {
        console.error('Error fetching live logs:', err);
      }
    }

    async function clearLogFiles() {
      await fetch('/api/logs/clear', { method: 'POST' });
      fetchLogs();
      showAlert('Log files cleared!');
    }

    function showAlert(msg) {
      const el = document.getElementById('alertBox');
      el.className = 'alert alert-success';
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 3000);
    }

    loadConfig();
    setInterval(fetchLogs, 1500);
    fetchLogs();
  </script>
</body>
</html>
"""

def read_log_tail(filename, lines_count=200):
    path = os.path.join(LOG_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-lines_count:])
        except Exception as e:
            return f"Error reading log: {e}"
    return None

if HAS_FLASK:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(load_config_file())

    @app.route("/api/config", methods=["POST"])
    def update_config():
        data = request.get_json(force=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON body"}), 400
        
        ok = save_config_file(data)
        if ok:
            return jsonify({"success": True, "message": "Updated config.json", "config": load_config_file()})
        else:
            return jsonify({"success": False, "error": "Failed writing to config.json"}), 500

    @app.route("/api/proxy/toggle-ports", methods=["POST"])
    def toggle_ports():
        data = request.get_json(force=True) or {}
        p_start = data.get("mtcm_port_start")
        p_end = data.get("mtcm_port_end")

        cfg = load_config_file()
        if p_start is not None:
            cfg["mtcm_port_start"] = int(p_start)
        if p_end is not None:
            cfg["mtcm_port_end"] = int(p_end)

        ok = save_config_file(cfg)
        return jsonify({"success": ok, "config": cfg})

    @app.route("/api/logs/full", methods=["GET"])
    def get_logs_full():
        res = read_log_tail("received_packets_full.txt")
        return jsonify({"content": res or "No raw socket packets recorded yet. (Check if logging is enabled)"})

    @app.route("/api/logs/data", methods=["GET"])
    def get_logs_data():
        res = read_log_tail("received_packets_data.txt")
        return jsonify({"content": res or "No unpacked payload data recorded yet. (Check if logging is enabled)"})

    @app.route("/api/logs/events", methods=["GET"])
    def get_logs_events():
        res = read_log_tail("mtcm_connection_events.txt")
        return jsonify({"content": res or "No MTCM connection events recorded yet."})

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        for filename in ["received_packets_full.txt", "received_packets_data.txt", "mtcm_connection_events.txt"]:
            p = os.path.join(LOG_DIR, filename)
            if os.path.exists(p):
                try: open(p, "w").close()
                except Exception: pass
        return jsonify({"success": True})

    def run_monitor_server(port=5000):
        print("===============================================================")
        print("   Starting Asymmetric Proxy Client Monitor & Settings UI (Flask)")
        print(f"   Config file: {CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print("===============================================================")
        app.run(host="0.0.0.0", port=port, debug=False)
else:
    class ProxyMonitorHTTPHandler(BaseHTTPRequestHandler):
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
            elif parsed.path == "/api/config":
                self._set_headers(200)
                self.wfile.write(json.dumps(load_config_file()).encode("utf-8"))
            elif parsed.path == "/api/logs/full":
                res = read_log_tail("received_packets_full.txt")
                self._set_headers(200)
                self.wfile.write(json.dumps({"content": res or "No raw socket packets recorded yet."}).encode("utf-8"))
            elif parsed.path == "/api/logs/data":
                res = read_log_tail("received_packets_data.txt")
                self._set_headers(200)
                self.wfile.write(json.dumps({"content": res or "No unpacked payload data recorded yet."}).encode("utf-8"))
            elif parsed.path == "/api/logs/events":
                res = read_log_tail("mtcm_connection_events.txt")
                self._set_headers(200)
                self.wfile.write(json.dumps({"content": res or "No MTCM connection events recorded yet."}).encode("utf-8"))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            body_str = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try: data = json.loads(body_str)
            except Exception: data = {}

            if parsed.path == "/api/config":
                ok = save_config_file(data)
                self._set_headers(200 if ok else 500)
                self.wfile.write(json.dumps({"success": ok, "config": load_config_file()}).encode("utf-8"))
            elif parsed.path == "/api/proxy/toggle-ports":
                cfg = load_config_file()
                if "mtcm_port_start" in data: cfg["mtcm_port_start"] = int(data["mtcm_port_start"])
                if "mtcm_port_end" in data: cfg["mtcm_port_end"] = int(data["mtcm_port_end"])
                ok = save_config_file(cfg)
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": ok, "config": cfg}).encode("utf-8"))
            elif parsed.path == "/api/logs/clear":
                for filename in ["received_packets_full.txt", "received_packets_data.txt", "mtcm_connection_events.txt"]:
                    p = os.path.join(LOG_DIR, filename)
                    if os.path.exists(p):
                        try: open(p, "w").close()
                        except Exception: pass
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def run_monitor_server(port=5000):
        print("===============================================================")
        print("   Starting Asymmetric Proxy Client Monitor & Settings UI (HTTP)")
        print(f"   Config file: {CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print("===============================================================")
        server = HTTPServer(("0.0.0.0", port), ProxyMonitorHTTPHandler)
        server.serve_forever()

if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_monitor_server(port)
