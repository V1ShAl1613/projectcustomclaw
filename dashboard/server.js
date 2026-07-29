import express from 'express';
import { exec, execSync, spawnSync } from 'child_process';
import { existsSync, readdirSync, statSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(express.json());
const WORKSPACE_ROOT = path.resolve(__dirname, '..');

app.use((_, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  next();
});

// ── Resolve Docker socket ──────────────────────────────────────────────────
// Docker Desktop on macOS uses a context-specific socket, not /var/run/docker.sock.
// We detect it by inspecting the active context so child processes (exec) can
// reach the daemon even when DOCKER_HOST is not set in the shell that started us.
function resolveDockerHost() {
  if (process.env.DOCKER_HOST) return process.env.DOCKER_HOST;
  try {
    const ctx = execSync('docker context inspect --format "{{.Endpoints.docker.Host}}"', {
      encoding: 'utf8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe'],
    }).trim().replace(/^"|"$/g, '');
    if (ctx) return ctx;
  } catch {}
  // Fallback candidates
  const candidates = [
    `/Users/${process.env.USER}/.docker/run/docker.sock`,
    '/var/run/docker.sock',
    '/run/docker.sock',
  ];
  for (const c of candidates) {
    if (existsSync(c)) return `unix://${c}`;
  }
  return undefined;
}

const DOCKER_HOST = resolveDockerHost();
console.log('Docker host:', DOCKER_HOST || '(using default)');

function buildEnv(extra = {}) {
  const env = { ...process.env, ...extra };
  if (DOCKER_HOST) env.DOCKER_HOST = DOCKER_HOST;
  return env;
}

// ── Claw definitions ───────────────────────────────────────────────────────
const CLAWS = {
  cloudDesktop: {
    name: 'Cloud Desktop',
    dir: path.resolve(__dirname),
    composeFile: 'docker-compose.yml',
    containers: ['cloud-desktop'],
    url: 'http://localhost:3010',
    description: 'Browser-based Linux desktop with terminal, browser, file manager, and workspace tools.',
    color: '#22c55e',
    extraEnv: {
      CLOUD_DESKTOP_PUID: String(process.getuid()),
      CLOUD_DESKTOP_PGID: String(process.getgid()),
    },
  },
  hermes: {
    name: 'Hermes Agent',
    dir: path.resolve(__dirname, '../hermes-agent'),
    // Override replaces network_mode:host with bridge + port mapping so
    // the dashboard is reachable from the macOS host browser.
    composeFile: 'docker-compose.yml -f docker-compose.override.yml',
    containers: ['hermes', 'hermes-dashboard'],
    url: 'http://localhost:9119',
    description: 'AI agent with gateway, dashboard and multi-channel support via s6-overlay.',
    color: '#aa3bff',
    extraEnv: {
      HERMES_UID: String(process.getuid()),
      HERMES_GID: String(process.getgid()),
    },
  },
  openclaw: {
    name: 'OpenClaw',
    dir: path.resolve(__dirname, '../openclaw'),
    // Override adds bridge networking + web UI service (mirrors hermes pattern)
    composeFile: 'docker-compose.yml -f docker-compose.override.yml',
    containers: ['openclaw-gateway', 'openclaw-ui'],
    url: 'http://localhost:5173',
    description: 'OpenClaw web UI — chat, sessions, settings, and multi-channel gateway.',
    color: '#f97316',
    // Tell compose to build the image locally instead of pulling 'openclaw:local'
    extraEnv: {
      OPENCLAW_IMAGE: 'openclaw:local',
    },
  },
};

// ── Docker helpers ─────────────────────────────────────────────────────────
function dockerPs() {
  try {
    const env = buildEnv();
    const out = execSync(
      "docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}|{{.Ports}}'",
      { encoding: 'utf8', timeout: 5000, env }
    );
    return out.trim().split('\n').filter(Boolean).map(line => {
      const [name, status, image, ports] = line.split('|');
      return { name, status, image, ports };
    });
  } catch {
    return [];
  }
}

// ── Routes ─────────────────────────────────────────────────────────────────
app.get('/api/claws', (_, res) => {
  const running = dockerPs();
  const result = Object.entries(CLAWS).map(([id, claw]) => {
    const activeContainers = claw.containers.map(c => {
      const found = running.find(r => r.name === c);
      return { name: c, running: !!found, status: found?.status || 'stopped', image: found?.image || '-' };
    });
    const isRunning = activeContainers.some(c => c.running);
    return { id, name: claw.name, description: claw.description, color: claw.color, url: claw.url, containers: activeContainers, isRunning };
  });
  res.json(result);
});

// Build the `-f file1 -f file2` flags for docker compose
function composeFlags(claw) {
  return claw.composeFile.split(' -f ').map(f => `-f ${f.trim()}`).join(' ');
}

app.post('/api/launch/:id', (req, res) => {
  const claw = CLAWS[req.params.id];
  if (!claw) return res.status(404).json({ error: 'Unknown claw' });

  const primaryFile = claw.composeFile.split(' ')[0];
  if (!existsSync(path.join(claw.dir, primaryFile))) {
    return res.status(400).json({ error: `docker-compose.yml not found in ${claw.dir}` });
  }

  const env = buildEnv(claw.extraEnv || {});
  const cmd = `docker compose ${composeFlags(claw)} up -d --build`;
  console.log(`[launch:${req.params.id}] ${cmd}`);

  exec(cmd, { cwd: claw.dir, env, timeout: 600000 }, (err, stdout, stderr) => {
    if (err) {
      console.error(`[launch:${req.params.id}] Error:`, stderr || err.message);
      return res.status(500).json({ error: stderr || err.message, stdout });
    }
    res.json({ ok: true, stdout, url: claw.url });
  });
});

app.post('/api/stop/:id', (req, res) => {
  const claw = CLAWS[req.params.id];
  if (!claw) return res.status(404).json({ error: 'Unknown claw' });

  const env = buildEnv(claw.extraEnv || {});
  exec(`docker compose ${composeFlags(claw)} down`, { cwd: claw.dir, env, timeout: 60000 }, (err, stdout, stderr) => {
    if (err) return res.status(500).json({ error: stderr || err.message });
    res.json({ ok: true, stdout });
  });
});

app.get('/api/logs/:id', (req, res) => {
  const claw = CLAWS[req.params.id];
  if (!claw) return res.status(404).json({ error: 'Unknown claw' });

  const env = buildEnv(claw.extraEnv || {});
  exec(`docker compose ${composeFlags(claw)} logs --tail=150 --no-color`, { cwd: claw.dir, env, timeout: 10000 }, (err, stdout, stderr) => {
    res.json({ logs: stdout || stderr || '' });
  });
});

// ── Health check ───────────────────────────────────────────────────────────
app.get('/api/health', (_, res) => res.json({ ok: true, dockerHost: DOCKER_HOST }));

app.get('/api/fs', (req, res) => {
  const target = typeof req.query.path === 'string' && req.query.path.trim() ? req.query.path : WORKSPACE_ROOT;
  const resolved = path.resolve(target);
  if (!resolved.startsWith(WORKSPACE_ROOT)) {
    return res.status(403).json({ error: 'Path escapes workspace root' });
  }
  try {
    const entries = readdirSync(resolved, { withFileTypes: true }).map((entry) => {
      const full = path.join(resolved, entry.name);
      const stat = statSync(full);
      return {
        name: entry.name,
        path: full,
        type: entry.isDirectory() ? 'dir' : 'file',
        size: stat.size,
        modified: stat.mtimeMs,
      };
    });
    res.json({ path: resolved, entries });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/terminal', (req, res) => {
  const command = typeof req.body?.command === 'string' ? req.body.command.trim() : '';
  const cwd = typeof req.body?.cwd === 'string' && req.body.cwd.trim() ? path.resolve(req.body.cwd) : WORKSPACE_ROOT;
  if (!command) {
    return res.status(400).json({ error: 'Command is required' });
  }
  if (!cwd.startsWith(WORKSPACE_ROOT)) {
    return res.status(403).json({ error: 'cwd escapes workspace root' });
  }

  exec(command, { cwd, env: buildEnv(), timeout: 20000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
    res.json({
      exitCode: err && typeof err.code === 'number' ? err.code : 0,
      output: (stdout || stderr || '').toString(),
      command,
      cwd,
      error: err ? String(err.message || err) : '',
    });
  });
});

app.listen(3001, () => {
  console.log('API server → http://localhost:3001');
  // Verify docker is reachable
  const check = spawnSync('docker', ['info'], { env: buildEnv(), encoding: 'utf8', timeout: 5000 });
  if (check.status !== 0) {
    console.warn('⚠️  Docker daemon not reachable. Launch buttons will fail until Docker Desktop is running.');
  } else {
    console.log('✓ Docker daemon reachable');
  }
});
