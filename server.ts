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

app.post('/api/proxy/restart', (req, res) => {
  if (proxyProcess) proxyProcess.kill('SIGTERM');
  setTimeout(() => {
    startProxyProcess();
    res.json({ success: true, message: 'Restarted Python proxy process.' });
  }, 1000);
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
