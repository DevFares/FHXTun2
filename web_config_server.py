#!/usr/bin/env python3
"""
Flask / Standard HTTP Web Configuration UI & REST API for Asymmetric Proxy Client.

Provides a clean browser dashboard and REST API to view and edit config.json.
Allows adjusting:
- Local & Remote Endpoints
- MTCM Port Ranges (e.g. 2525 - 2530)
- Max MTCM Active Connection Limits
- Socket Connection Idle Timeout
- Socket Buffer Sizes & Log Levels

Run:
  python web_config_server.py
Access UI:
  http://127.0.0.1:5000
"""

import os
import json
import logging
import sys
import webbrowser
import threading


def _open_browser_url(port: int) -> None:
    """Helper to open the configuration web interface in the default browser."""
    try:
        url = f"http://127.0.0.1:{port}"
        logger.info(f"Opening browser configuration page at {url}")
        webbrowser.open(url)
    except Exception as err:
        logger.warning(f"Could not automatically open web browser: {err}")

# Try importing Flask; if missing, fallback to standard library WSGI/HTTP server
try:
    from flask import Flask, request, jsonify, render_template_string
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

from asymmetric_proxy.config import (
    CONFIG_FILE_PATH,
    load_config_file,
    save_config_file,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web_config_server")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Asymmetric Proxy Configuration Editor</title>
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
      background: rgba(16, 185, 129, 0.1);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
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
      color: var(--cyan);
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
    input:focus, select:focus { border-color: var(--cyan); }
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
    .filepath { font-family: monospace; color: var(--cyan); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Asymmetric Proxy Configuration Editor</h1>
        <div class="subtitle">Modifying config file: <span class="filepath">{{ config_path }}</span></div>
      </div>
      <div class="badge">Flask Web Config Server</div>
    </header>

    <div id="alertBox" class="alert"></div>

    <form id="configForm" onsubmit="saveConfig(event)">
      <div class="card">
        <div class="card-title">Local & Remote Endpoints</div>
        <div class="form-grid">
          <div class="form-group">
            <label>Local Ingress Host</label>
            <input type="text" id="local_host" name="local_host" value="{{ config.local_host }}" required>
            <span class="help-text">Local interface for SOCKS/TCP proxy listener</span>
          </div>
          <div class="form-group">
            <label>Local Ingress Port</label>
            <input type="number" id="local_port" name="local_port" value="{{ config.local_port }}" required>
            <span class="help-text">Local port (e.g. 1080)</span>
          </div>
          <div class="form-group">
            <label>Remote Proxy Host</label>
            <input type="text" id="remote_proxy_host" name="remote_proxy_host" value="{{ config.remote_proxy_host }}" required>
            <span class="help-text">IP of Remote Asymmetric Server</span>
          </div>
          <div class="form-group">
            <label>Remote UDP Port (UCMC)</label>
            <input type="number" id="remote_udp_port" name="remote_udp_port" value="{{ config.remote_udp_port }}" required>
            <span class="help-text">Outbound UDP target port (e.g. 9090)</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Client MultiTCP Connection Pool (MTCM -> Server MTCMS)</div>
        <div class="form-grid">
          <div class="form-group">
            <label>MTCM Port Start Range</label>
            <input type="number" id="mtcm_port_start" name="mtcm_port_start" value="{{ config.mtcm_port_start }}" required>
            <span class="help-text">First remote TCP return port on Server MTCMS to connect to (e.g. 2525)</span>
          </div>
          <div class="form-group">
            <label>MTCM Port End Range</label>
            <input type="number" id="mtcm_port_end" name="mtcm_port_end" value="{{ config.mtcm_port_end }}" required>
            <span class="help-text">Last remote TCP return port on Server MTCMS to connect to (e.g. 2530)</span>
          </div>
          <div class="form-group">
            <label>Max MTCM Active Sockets</label>
            <input type="number" id="max_mtcm_connections" name="max_mtcm_connections" value="{{ config.max_mtcm_connections }}" required>
            <span class="help-text">Maximum allowed active concurrent TCP connections</span>
          </div>
          <div class="form-group">
            <label>Socket Idle Timeout (Seconds)</label>
            <input type="number" id="socket_timeout" name="socket_timeout" value="{{ config.socket_timeout }}" required>
            <span class="help-text">Inactivity limit before closing socket</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">HTTP Response Obfuscation & Packet Spoofing (DPI Bypass)</div>
        <div class="form-grid">
          <div class="form-group" style="grid-column: 1 / -1;">
            <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: #fff;">
              <input type="checkbox" id="http_obfuscation_enabled" name="http_obfuscation_enabled" {% if config.http_obfuscation_enabled %}checked{% endif %} style="width: 18px; height: 18px; accent-color: var(--cyan);">
              Enable HTTP Response Obfuscation (Wrap Return Data in HTTP 304 Spoofed Headers + Hex Payload)
            </label>
            <span class="help-text" style="margin-top: 4px;">When enabled, proxy return data is encapsulated inside a legitimate HTTP response header with hex-encoded payload to pass undetected through Deep Packet Inspection (DPI) and firewalls.</span>
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Spoofed HTTP Response Header Template</label>
            <textarea id="http_spoof_header_template" name="http_spoof_header_template" rows="7" style="font-family: monospace; font-size: 13px; background: #0f172a; border: 1px solid var(--border); color: #38bdf8; padding: 10px; border-radius: 6px; width: 100%; outline: none;">{{ config.http_spoof_header_template }}</textarea>
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
        <button type="submit">Save Configuration File</button>
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
        if (['local_port', 'remote_udp_port', 'mtcm_port_start', 'mtcm_port_end', 'max_mtcm_connections', 'socket_timeout', 'socket_buffer_size', 'chunk_read_size'].includes(key)) {
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
          alertEl.textContent = 'Configuration successfully saved to config.json! Python proxy will use new parameters on next start/reload.';
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
        cfg = load_config_file()
        return render_template_string(HTML_TEMPLATE, config=cfg, config_path=CONFIG_FILE_PATH)

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

    def run_server(port=5000):
        print(f"===============================================================")
        print(f"   Starting Flask Web Config Server")
        print(f"   Config file: {CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print(f"===============================================================")
        threading.Timer(0.8, _open_browser_url, args=(port,)).start()
        app.run(host="0.0.0.0", port=port, debug=False)

else:
    class StandaloneConfigHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/config":
                cfg = load_config_file()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(cfg).encode("utf-8"))
            else:
                cfg = load_config_file()
                html = render_html_manual(cfg, CONFIG_FILE_PATH)
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
                    ok = save_config_file(data)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": ok, "config": load_config_file()}).encode("utf-8"))
                except Exception as err:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": str(err)}).encode("utf-8"))

    def run_server(port=5000):
        print(f"===============================================================")
        print(f"   Starting Web Config Server (Standalone HTTP mode)")
        print(f"   Config file: {CONFIG_FILE_PATH}")
        print(f"   Open UI: http://127.0.0.1:{port}")
        print(f"===============================================================")
        threading.Timer(0.8, _open_browser_url, args=(port,)).start()
        server = HTTPServer(("0.0.0.0", port), StandaloneConfigHandler)
        server.serve_forever()


if __name__ == "__main__":
    server_port = 5000
    if len(sys.argv) > 1:
        try:
            server_port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(server_port)
