#!/usr/bin/env python3
"""
Flask / Standard HTTP Web Configuration UI & REST API for Asymmetric Proxy Server.

Provides a clean browser dashboard and REST API to view and edit server_config.json.
Allows adjusting:
- Inbound UDP Listener Host & Port (UCMS)
- Client TCP Return Target Host & Port Ranges (MTCMS)
- Maximum Active Concurrent Sessions & Socket Timeouts (TIS)
- Socket Buffer Sizes, Read Chunk Sizes, and Log Levels

Run:
  python3 -m asymmetric_server.web_config.web_config_server
  OR
  python3 asymmetric_server/web_config/web_config_server.py
Access UI:
  http://127.0.0.1:5001
"""

import os
import json
import logging
import sys
import webbrowser
import threading


def _open_browser_url(port: int) -> None:
    """Helper to open the server configuration web interface in the default browser."""
    try:
        url = f"http://127.0.0.1:{port}"
        logger.info(f"Opening browser server configuration page at {url}")
        webbrowser.open(url)
    except Exception as err:
        logger.warning(f"Could not automatically open web browser: {err}")

# Ensure parent project root is in sys.path for relative/module imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Try importing Flask; if missing, fallback to standard library WSGI/HTTP server
try:
    from flask import Flask, request, jsonify, render_template_string
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

from asymmetric_server.config import (
    SERVER_CONFIG_FILE_PATH,
    load_server_config_file,
    save_server_config_file,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server_web_config")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Asymmetric Proxy Server Configuration Editor</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-dim: #94a3b8;
      --accent: #9333ea;
      --accent-hover: #7e22ce;
      --success: #10b981;
      --purple: #c084fc;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 32px 16px;
      line-height: 1.5;
    }
    .container { max-width: 800px; margin: 0 auto; }
    header {
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    h1 { font-size: 22px; font-weight: 700; color: #fff; }
    .subtitle { font-size: 13px; color: var(--text-dim); margin-top: 4px; }
    .badge {
      background: rgba(192, 132, 252, 0.12);
      color: var(--purple);
      border: 1px solid rgba(192, 132, 252, 0.3);
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-family: monospace;
    }
    .alert {
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 20px;
      font-size: 14px;
      display: none;
    }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #34d399; }
    .alert-error { background: rgba(244, 63, 94, 0.15); border: 1px solid #f43f5e; color: #fca5a5; }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 20px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      color: var(--purple);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    label { font-size: 13px; font-weight: 500; color: var(--text-dim); }
    input, select {
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 6px;
      font-size: 14px;
      font-family: monospace;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: var(--purple); }
    .help-text { font-size: 11px; color: #64748b; }

    .actions {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
      margin-top: 24px;
    }
    button {
      background: var(--accent);
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: var(--accent-hover); }
    button.secondary { background: #334155; }
    button.secondary:hover { background: #475569; }
    .filepath { font-family: monospace; color: var(--purple); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Asymmetric Proxy Server Configuration Editor</h1>
        <div class="subtitle">Modifying config file: <span class="filepath">{{ config_path }}</span></div>
      </div>
      <div class="badge">Server Web Config</div>
    </header>

    <div id="alertBox" class="alert"></div>

    <form id="configForm" onsubmit="saveConfig(event)">
      <div class="card">
        <div class="card-title">UDP Inbound Listener (UCMS)</div>
        <div class="form-grid">
          <div class="form-group">
            <label>UDP Bind Host</label>
            <input type="text" id="bind_udp_host" name="bind_udp_host" value="{{ config.bind_udp_host }}" required>
            <span class="help-text">IP interface for incoming UDP packets (e.g. 0.0.0.0)</span>
          </div>
          <div class="form-group">
            <label>UDP Bind Port</label>
            <input type="number" id="bind_udp_port" name="bind_udp_port" value="{{ config.bind_udp_port }}" required>
            <span class="help-text">Inbound UDP receiver port (e.g. 9090)</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Client TCP Return Target Channel (MTCMS)</div>
        <div class="form-grid">
          <div class="form-group">
            <label>Server TCP Bind Host</label>
            <input type="text" id="bind_tcp_host" name="bind_tcp_host" value="{{ config.bind_tcp_host }}" required>
            <span class="help-text">IP interface where MTCMS listens for client TCP return connections (e.g. 0.0.0.0). MTCMS accepts socket connections from Client Proxy and routes return traffic through them.</span>
          </div>
          <div class="form-group">
            <label>Return TCP Port Start</label>
            <input type="number" id="bind_tcp_port_start" name="bind_tcp_port_start" value="{{ config.bind_tcp_port_start or config.client_tcp_port_start }}" required>
            <span class="help-text">First return TCP listening port in pool (e.g. 2525)</span>
          </div>
          <div class="form-group">
            <label>Return TCP Port End</label>
            <input type="number" id="bind_tcp_port_end" name="bind_tcp_port_end" value="{{ config.bind_tcp_port_end or config.client_tcp_port_end }}" required>
            <span class="help-text">Last return TCP listening port in pool (e.g. 2530)</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Session & Inactivity Controls (TIS)</div>
        <div class="form-grid">
          <div class="form-group">
            <label>Max Active Sessions</label>
            <input type="number" id="max_active_sessions" name="max_active_sessions" value="{{ config.max_active_sessions }}" required>
            <span class="help-text">Maximum parallel session slots (1 to 65535)</span>
          </div>
          <div class="form-group">
            <label>Socket Idle Timeout (Seconds)</label>
            <input type="number" id="socket_timeout" name="socket_timeout" value="{{ config.socket_timeout }}" required>
            <span class="help-text">Inactivity limit before dropping target socket</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">HTTP Response Obfuscation & Packet Spoofing (DPI Bypass)</div>
        <div class="form-grid">
          <div class="form-group" style="grid-column: 1 / -1;">
            <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: #fff;">
              <input type="checkbox" id="http_obfuscation_enabled" name="http_obfuscation_enabled" {% if config.http_obfuscation_enabled %}checked{% endif %} style="width: 18px; height: 18px; accent-color: var(--purple);">
              Enable HTTP Response Obfuscation (Wrap Return Data in HTTP 304 Spoofed Headers + Hex Payload)
            </label>
            <span class="help-text" style="margin-top: 4px;">When enabled, outgoing TCP return response frames generated by MTCMS will be encapsulated within a spoofed HTTP 304 response with a hex-encoded body payload to bypass DPI detection.</span>
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Spoofed HTTP Response Header Template</label>
            <textarea id="http_spoof_header_template" name="http_spoof_header_template" rows="7" style="font-family: monospace; font-size: 13px; background: #0f172a; border: 1px solid var(--border); color: #c084fc; padding: 10px; border-radius: 6px; width: 100%; outline: none;">{{ config.http_spoof_header_template }}</textarea>
            <span class="help-text">Dynamic placeholders supported: <code>{date}</code>, <code>{etag}</code>, <code>{headernb}</code>. Headers must terminate with double CRLF (<code>\r\n\r\n</code>).</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Performance Tuning & Logging</div>
        <div class="form-grid">
          <div class="form-group">
            <label>Socket Buffer Size (Bytes)</label>
            <input type="number" id="socket_buffer_size" name="socket_buffer_size" value="{{ config.socket_buffer_size }}" required>
            <span class="help-text">OS Send/Receive buffer (e.g. 1048576 for 1MB)</span>
          </div>
          <div class="form-group">
            <label>Chunk Read Size (Bytes)</label>
            <input type="number" id="chunk_read_size" name="chunk_read_size" value="{{ config.chunk_read_size }}" required>
            <span class="help-text">Read size per loop (e.g. 65536)</span>
          </div>
          <div class="form-group">
            <label>Logging Verbosity</label>
            <select id="log_level" name="log_level">
              <option value="DEBUG" {% if config.log_level == "DEBUG" %}selected{% endif %}>DEBUG</option>
              <option value="INFO" {% if config.log_level == "INFO" %}selected{% endif %}>INFO</option>
              <option value="WARNING" {% if config.log_level == "WARNING" %}selected{% endif %}>WARNING</option>
              <option value="ERROR" {% if config.log_level == "ERROR" %}selected{% endif %}>ERROR</option>
            </select>
            <span class="help-text">Log level output</span>
          </div>
        </div>
      </div>

      <div class="actions">
        <button type="button" class="secondary" onclick="reloadForm()">Reset to Saved File</button>
        <button type="submit">Save Server Configuration</button>
      </div>
    </form>
  </div>

  <script>
    async function saveConfig(e) {
      e.preventDefault();
      const form = document.getElementById('configForm');
      const formData = new FormData(form);
      const data = {};
      
      formData.forEach((value, key) => {
        if (['bind_udp_port', 'bind_tcp_port_start', 'bind_tcp_port_end', 'client_tcp_port_start', 'client_tcp_port_end', 'max_active_sessions', 'socket_timeout', 'socket_buffer_size', 'chunk_read_size'].includes(key)) {
          data[key] = parseInt(value, 10);
        } else if (key === 'http_obfuscation_enabled') {
          data[key] = true;
        } else {
          data[key] = value;
        }
      });
      if (!formData.has('http_obfuscation_enabled')) {
        data['http_obfuscation_enabled'] = false;
      }

      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        const result = await res.json();
        const alertEl = document.getElementById('alertBox');
        
        if (result.success) {
          alertEl.className = 'alert alert-success';
          alertEl.textContent = 'Configuration successfully saved to server_config.json! Proxy server will use new parameters on next start/reload.';
          alertEl.style.display = 'block';
        } else {
          alertEl.className = 'alert alert-error';
          alertEl.textContent = 'Failed to save configuration: ' + (result.error || 'Unknown error');
          alertEl.style.display = 'block';
        }
      } catch (err) {
        alert('Error saving configuration: ' + err.message);
      }
    }

    async function reloadForm() {
      location.reload();
    }
  </script>
</body>
</html>
"""


def render_html_manual(config_dict, config_path):
    """Fallback template renderer for standard library HTTP server mode."""
    html = HTML_TEMPLATE
    html = html.replace("{{ config_path }}", config_path)

    if config_dict.get("http_obfuscation_enabled"):
        html = html.replace("{% if config.http_obfuscation_enabled %}checked{% endif %}", "checked")
    else:
        html = html.replace("{% if config.http_obfuscation_enabled %}checked{% endif %}", "")
    
    for key, val in config_dict.items():
        placeholder = "{{ config." + key + " }}"
        html = html.replace(placeholder, str(val))
    
    for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        key_str = f'value="{level}" {{% if config.log_level == "{level}" %}}selected{{% endif %}}'
        if config_dict.get("log_level") == level:
            html = html.replace(key_str, f'value="{level}" selected')
        else:
            html = html.replace(key_str, f'value="{level}"')
            
    return html


if HAS_FLASK:
    app = Flask(__name__)

    @app.route("/")
    def index():
        cfg = load_server_config_file()
        return render_template_string(HTML_TEMPLATE, config=cfg, config_path=SERVER_CONFIG_FILE_PATH)

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(load_server_config_file())

    @app.route("/api/config", methods=["POST"])
    def update_config():
        data = request.get_json(force=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON body"}), 400
        
        ok = save_server_config_file(data)
        if ok:
            return jsonify({"success": True, "message": "Updated server_config.json", "config": load_server_config_file()})
        else:
            return jsonify({"success": False, "error": "Failed writing to server_config.json"}), 500

    def run_server(port=5001):
        print(f"===============================================================")
        print(f"   Starting Flask Server Proxy Web Config Server")
        print(f"   Config file: {SERVER_CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print(f"===============================================================")
        threading.Timer(0.8, _open_browser_url, args=(port,)).start()
        app.run(host="0.0.0.0", port=port, debug=False)

else:
    class StandaloneServerConfigHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/config":
                cfg = load_server_config_file()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(cfg).encode("utf-8"))
            else:
                cfg = load_server_config_file()
                html = render_html_manual(cfg, SERVER_CONFIG_FILE_PATH)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/config":
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body.decode('utf-8'))
                    ok = save_server_config_file(data)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": ok, "config": load_server_config_file()}).encode("utf-8"))
                except Exception as err:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": str(err)}).encode("utf-8"))

    def run_server(port=5001):
        print(f"===============================================================")
        print(f"   Starting Server Web Config (Standalone HTTP mode)")
        print(f"   Config file: {SERVER_CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print(f"===============================================================")
        threading.Timer(0.8, _open_browser_url, args=(port,)).start()
        server = HTTPServer(("0.0.0.0", port), StandaloneServerConfigHandler)
        server.serve_forever()


if __name__ == "__main__":
    server_port = 5001
    if len(sys.argv) > 1:
        try:
            server_port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(server_port)
