import express from 'express';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';

const app = express();
const PORT = 3000;

app.use(express.json());

let proxyProcess: ChildProcess | null = null;
let proxyStatus: 'stopped' | 'running' | 'error' = 'stopped';
let logBuffer: string[] = [];
const MAX_LOG_LINES = 1000;

let metrics = {
  activeSessions: 0,
  totalSessions: 0,
  udpPacketsSent: 0,
  udpBytesSent: 0,
  tcpPacketsReceived: 0,
  tcpBytesReceived: 0,
};

let startTime: number | null = null;

function appendLog(line: string) {
  const time = new Date().toISOString().split('T')[1].slice(0, 8);
  logBuffer.push(`[${time}] ${line}`);
  if (logBuffer.length > MAX_LOG_LINES) {
    logBuffer.shift();
  }
}

function startProxyProcess() {
  if (proxyProcess) return;

  appendLog('Starting Python Asymmetric Proxy (main.py)...');
  const mainPath = path.join(process.cwd(), 'main.py');

  proxyProcess = spawn('python3', [mainPath], {
    env: { ...process.env, PYTHONUNBUFFERED: '1', LOG_LEVEL: 'DEBUG' },
  });

  proxyStatus = 'running';
  startTime = Date.now();

  proxyProcess.stdout?.on('data', (data) => {
    const lines = data.toString().split('\n');
    lines.forEach((line: string) => {
      if (line.trim()) {
        appendLog(line.trim());
        if (line.includes('Session') && line.includes('CREATED')) {
          metrics.totalSessions++;
          metrics.activeSessions++;
        }
        if (line.includes('Session') && line.includes('CLOSING')) {
          metrics.activeSessions = Math.max(0, metrics.activeSessions - 1);
        }
        if (line.includes('sent') && line.includes('UDP')) {
          metrics.udpPacketsSent++;
          metrics.udpBytesSent += 512;
        }
        if (line.includes('Unpacked incoming TCP')) {
          metrics.tcpPacketsReceived++;
          metrics.tcpBytesReceived += 1024;
        }
      }
    });
  });

  proxyProcess.stderr?.on('data', (data) => {
    const lines = data.toString().split('\n');
    lines.forEach((line: string) => {
      if (line.trim()) {
        appendLog(`[STDERR] ${line.trim()}`);
      }
    });
  });

  proxyProcess.on('close', (code) => {
    appendLog(`Python process exited with code ${code}`);
    proxyStatus = 'stopped';
    proxyProcess = null;
  });

  proxyProcess.on('error', (err) => {
    appendLog(`Python process error: ${err.message}`);
    proxyStatus = 'error';
    proxyProcess = null;
  });
}

// Auto-start python proxy on server boot
startProxyProcess();

// API Routes
app.get('/api/proxy/status', (req, res) => {
  const uptime = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0;
  res.json({
    status: proxyStatus,
    pid: proxyProcess?.pid || null,
    metrics: { ...metrics, uptimeSeconds: uptime },
  });
});

app.get('/api/proxy/logs', (req, res) => {
  res.json({ logs: logBuffer });
});

// Config File API
const configPath = path.join(process.cwd(), 'config.json');

app.get('/api/config', (req, res) => {
  try {
    if (fs.existsSync(configPath)) {
      const data = fs.readFileSync(configPath, 'utf8');
      res.json(JSON.parse(data));
    } else {
      res.status(404).json({ error: 'config.json not found' });
    }
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/config', (req, res) => {
  try {
    const newConfig = req.body;
    fs.writeFileSync(configPath, JSON.stringify(newConfig, null, 2), 'utf8');
    appendLog('[CONFIG] Updated config.json file successfully.');
    res.json({ success: true, message: 'Saved config.json' });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/proxy/toggle-ports', (req, res) => {
  try {
    const { mtcm_port_start, mtcm_port_end } = req.body;
    if (fs.existsSync(configPath)) {
      const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      if (mtcm_port_start !== undefined) cfg.mtcm_port_start = Number(mtcm_port_start);
      if (mtcm_port_end !== undefined) cfg.mtcm_port_end = Number(mtcm_port_end);
      fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2), 'utf8');
      appendLog(`[PORTS] Updated MTCM port range: ${cfg.mtcm_port_start} - ${cfg.mtcm_port_end}`);
      res.json({ success: true, config: cfg });
    } else {
      res.status(404).json({ error: 'config.json not found' });
    }
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Packet Logging APIs
const logsDir = path.join(process.cwd(), 'logs');

app.get('/api/logs/full', (req, res) => {
  const p = path.join(logsDir, 'received_packets_full.txt');
  if (fs.existsSync(p)) {
    try {
      const content = fs.readFileSync(p, 'utf8');
      const lines = content.split('\n');
      res.json({ content: lines.slice(-200).join('\n') });
    } catch (e: any) {
      res.json({ content: `Error reading log: ${e.message}` });
    }
  } else {
    res.json({ content: 'No raw socket packets recorded yet. (Check if write_received_packets_full is enabled in config.json)' });
  }
});

app.get('/api/logs/data', (req, res) => {
  const p = path.join(logsDir, 'received_packets_data.txt');
  if (fs.existsSync(p)) {
    try {
      const content = fs.readFileSync(p, 'utf8');
      const lines = content.split('\n');
      res.json({ content: lines.slice(-200).join('\n') });
    } catch (e: any) {
      res.json({ content: `Error reading log: ${e.message}` });
    }
  } else {
    res.json({ content: 'No unpacked payload data recorded yet. (Check if write_received_packets_data is enabled in config.json)' });
  }
});

app.get('/api/logs/events', (req, res) => {
  const p = path.join(logsDir, 'mtcm_connection_events.txt');
  if (fs.existsSync(p)) {
    try {
      const content = fs.readFileSync(p, 'utf8');
      const lines = content.split('\n');
      res.json({ content: lines.slice(-200).join('\n') });
    } catch (e: any) {
      res.json({ content: `Error reading log: ${e.message}` });
    }
  } else {
    res.json({ content: 'No MTCM connection events recorded yet.' });
  }
});

app.post('/api/logs/clear', (req, res) => {
  ['received_packets_full.txt', 'received_packets_data.txt', 'mtcm_connection_events.txt'].forEach(f => {
    const p = path.join(logsDir, f);
    if (fs.existsSync(p)) {
      try { fs.writeFileSync(p, '', 'utf8'); } catch (e) {}
    }
  });
  res.json({ success: true });
});

// Proxy Enabler Integration
const enablerStateFile = path.join(process.cwd(), 'proxy_enabler', 'proxy_enabler_state.json');

app.get('/api/proxy-enabler/status', (req, res) => {
  if (fs.existsSync(enablerStateFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(enablerStateFile, 'utf8'));
      return res.json(data);
    } catch (e) {}
  }
  res.json({ enabled: false, route_mode: 'http_https_tcp_udp', proxy_host: '127.0.0.1', proxy_port: 1080 });
});

app.post('/api/proxy-enabler/toggle', (req, res) => {
  let state = { enabled: false, route_mode: 'http_https_tcp_udp', proxy_host: '127.0.0.1', proxy_port: 1080 };
  if (fs.existsSync(enablerStateFile)) {
    try { state = { ...state, ...JSON.parse(fs.readFileSync(enablerStateFile, 'utf8')) }; } catch (e) {}
  }
  state.enabled = req.body.enabled !== undefined ? Boolean(req.body.enabled) : !state.enabled;
  try {
    fs.mkdirSync(path.dirname(enablerStateFile), { recursive: true });
    fs.writeFileSync(enablerStateFile, JSON.stringify(state, null, 2), 'utf8');
  } catch (e) {}
  res.json({ success: true, state });
});

app.post('/api/proxy-enabler/route-option', (req, res) => {
  let state = { enabled: false, route_mode: 'http_https_tcp_udp', proxy_host: '127.0.0.1', proxy_port: 1080 };
  if (fs.existsSync(enablerStateFile)) {
    try { state = { ...state, ...JSON.parse(fs.readFileSync(enablerStateFile, 'utf8')) }; } catch (e) {}
  }
  if (req.body.route_mode) state.route_mode = req.body.route_mode;
  try {
    fs.mkdirSync(path.dirname(enablerStateFile), { recursive: true });
    fs.writeFileSync(enablerStateFile, JSON.stringify(state, null, 2), 'utf8');
  } catch (e) {}
  res.json({ success: true, state });
});

app.post('/api/proxy/test-packet', (req, res) => {
  appendLog('[TEST BURST] Simulating 5G packet burst...');
  metrics.totalSessions++;
  metrics.activeSessions++;
  metrics.udpPacketsSent += 5;
  metrics.udpBytesSent += 2560;
  metrics.tcpPacketsReceived += 5;
  metrics.tcpBytesReceived += 5120;

  setTimeout(() => {
    metrics.activeSessions = Math.max(0, metrics.activeSessions - 1);
  }, 2000);

  res.json({ success: true });
});

// Serve static index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(process.cwd(), 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Node runner listening on http://0.0.0.0:${PORT}`);
});
