import { useEffect, useMemo, useState } from 'react';
import type { Page } from './App';

const API = 'http://localhost:3001';
const ROOTS = [
  { label: 'Workspace', path: '..' },
  { label: 'Dashboard', path: '.' },
  { label: 'Cloud Desktop', path: './cloud-desktop' },
  { label: 'Hermes', path: '../hermes-agent' },
  { label: 'OpenClaw', path: '../openclaw' },
];

interface Entry {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size: number;
  modified: number;
}

interface Claw {
  id: string;
  name: string;
  color: string;
  url: string;
  isRunning: boolean;
}

interface WindowState {
  id: string;
  title: string;
  kind: 'terminal' | 'browser' | 'files' | 'claw';
  x: number;
  y: number;
  w: number;
  h: number;
}

const DEFAULT_WINDOWS: WindowState[] = [
  { id: 'files', title: 'Files', kind: 'files', x: 24, y: 24, w: 360, h: 380 },
  { id: 'terminal', title: 'Terminal', kind: 'terminal', x: 410, y: 24, w: 560, h: 380 },
  { id: 'browser', title: 'Browser', kind: 'browser', x: 24, y: 428, w: 946, h: 300 },
];

function fmtBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Desktop({ onNavigate, onOpenViewer }: {
  onNavigate: (p: Page) => void;
  onOpenViewer: (url: string, title: string, color: string) => void;
}) {
  const [windows, setWindows] = useState(DEFAULT_WINDOWS);
  const [cwd, setCwd] = useState('..');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [command, setCommand] = useState('pwd');
  const [output, setOutput] = useState('Ready.');
  const [browserUrl, setBrowserUrl] = useState('http://localhost:3010');
  const [browserCurrentUrl, setBrowserCurrentUrl] = useState('http://localhost:3010');
  const [claws, setClaws] = useState<Claw[]>([]);
  const [selectedClaw, setSelectedClaw] = useState<string>('hermes');
  const [launching, setLaunching] = useState(false);

  const selected = claws.find((claw) => claw.id === selectedClaw);

  const fetchClaws = () => {
    fetch(`${API}/api/claws`).then((r) => r.json()).then(setClaws).catch(() => undefined);
  };

  const fetchFiles = (pathValue = cwd) => {
    setCwd(pathValue);
    fetch(`${API}/api/fs?path=${encodeURIComponent(pathValue)}`)
      .then((r) => r.json())
      .then((data) => setEntries(data.entries || []))
      .catch(() => setEntries([]));
  };

  useEffect(() => {
    fetchClaws();
    fetchFiles();
    const t = setInterval(fetchClaws, 4000);
    return () => clearInterval(t);
  }, []);

  const runCommand = async () => {
    setOutput('Running...');
    const res = await fetch(`${API}/api/terminal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, cwd }),
    });
    const data = await res.json();
    setOutput([data.output, data.error ? `\n[error] ${data.error}` : ''].join(''));
    fetchFiles(cwd);
  };

  const launchClaw = async (id: string) => {
    setLaunching(true);
    await fetch(`${API}/api/launch/${id}`, { method: 'POST' }).catch(() => undefined);
    setLaunching(false);
    fetchClaws();
  };

  const updateWindow = (id: string, patch: Partial<WindowState>) => {
    setWindows((current) => current.map((win) => (win.id === id ? { ...win, ...patch } : win)));
  };

  const normalizeBrowserUrl = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return 'about:blank';
    if (/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(trimmed)) return trimmed;
    return `https://${trimmed}`;
  };

  const windowClasses = useMemo(() => new Set(windows.map((w) => w.kind)), [windows]);

  return (
    <div className="desktop-shell">
      <div className="desktop-wallpaper">
        <div className="desktop-orb desktop-orb--one" />
        <div className="desktop-orb desktop-orb--two" />
        <div className="desktop-orb desktop-orb--three" />
      </div>

      <header className="desktop-topbar">
        <div>
          <div className="desktop-kicker">Cloud Computer</div>
          <div className="desktop-title">Full VM access for Hermes + OpenClaw</div>
        </div>
        <div className="desktop-topbar-actions">
          <button className="btn btn-ghost" onClick={() => onOpenViewer('http://localhost:3010', 'Cloud Desktop', '#22c55e')}>Open VM</button>
          <button className="btn btn-ghost" onClick={() => onNavigate('home')}>Claws</button>
          <button className="btn btn-ghost" onClick={() => onNavigate('dashboard')}>Status</button>
          <button className="btn btn-primary" onClick={() => onNavigate('chat')}>Chat</button>
        </div>
      </header>

      <section className="desktop-grid">
        <aside className="desktop-sidebar-panel">
          <div className="panel-card">
            <div className="panel-title">Main Launchpad</div>
            <div className="launch-grid">
              <button className="launch-tile launch-tile--primary" onClick={() => onOpenViewer('http://localhost:3010', 'Cloud Desktop', '#22c55e')}>
                <span className="launch-tile-icon">🖥️</span>
                <span className="launch-tile-label">Open VM</span>
                <span className="launch-tile-meta">Cloud desktop</span>
              </button>
              <button className="launch-tile" onClick={() => onOpenViewer('http://localhost:9119', 'Hermes', '#aa3bff')}>
                <span className="launch-tile-icon">🧠</span>
                <span className="launch-tile-label">Hermes</span>
                <span className="launch-tile-meta">Full control access</span>
              </button>
              <button className="launch-tile" onClick={() => onOpenViewer('http://localhost:18789', 'OpenClaw', '#f97316')}>
                <span className="launch-tile-icon">🦞</span>
                <span className="launch-tile-label">OpenClaw</span>
                <span className="launch-tile-meta">Gateway + UI</span>
              </button>
              <button className="launch-tile" onClick={() => setWindows((wins) => [...wins.slice(1), wins[0]])}>
                <span className="launch-tile-icon">⌨️</span>
                <span className="launch-tile-label">Terminal</span>
                <span className="launch-tile-meta">Shell access</span>
              </button>
            </div>
          </div>

          <div className="panel-card">
            <div className="panel-title">Connected Claws</div>
            <div className="claw-mini-list">
              {claws.map((claw) => (
                <button
                  key={claw.id}
                  className={`claw-mini ${selectedClaw === claw.id ? 'active' : ''}`}
                  onClick={() => setSelectedClaw(claw.id)}
                >
                  <span className="claw-mini-dot" style={{ background: claw.color }} />
                  <span>{claw.name}</span>
                  <span className={`claw-mini-state ${claw.isRunning ? 'live' : ''}`}>{claw.isRunning ? 'live' : 'stopped'}</span>
                </button>
              ))}
            </div>
            {selected && (
              <button
                className="panel-launch panel-launch--accent"
                onClick={() => launchClaw(selected.id)}
                disabled={launching}
              >
                {selected.isRunning ? 'Refresh' : `Launch ${selected.name}`}
              </button>
            )}
          </div>

          <div className="panel-card">
            <div className="panel-title">Workspaces</div>
            <div className="workspace-list">
              {ROOTS.map((root) => (
                <button key={root.path} className="workspace-item" onClick={() => fetchFiles(root.path)}>
                  <strong>{root.label}</strong>
                  <span>{root.path}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <main className="desktop-stage">
          <div className="desktop-startbar">
            <button className="start-button" onClick={() => setWindows((wins) => [wins[0], ...wins.slice(1)])}>Start</button>
            <input className="start-search" value={browserUrl} onChange={(e) => setBrowserUrl(e.target.value)} placeholder="Search or type a URL" />
            <div className="start-pinned">
              <button className="start-pin start-pin--accent" onClick={() => onOpenViewer('http://localhost:3010', 'Cloud Desktop', '#22c55e')}>VM</button>
              <button className="start-pin" onClick={() => onOpenViewer('http://localhost:9119', 'Hermes', '#aa3bff')}>Hermes</button>
              <button className="start-pin" onClick={() => onOpenViewer('http://localhost:18789', 'OpenClaw', '#f97316')}>OpenClaw</button>
              <button className="start-pin" onClick={() => setWindows((wins) => [...wins.slice(1), wins[0]])}>Terminal</button>
              <button className="start-pin" onClick={() => setWindows((wins) => [wins[2], ...wins.slice(0, 2)])}>Browser</button>
            </div>
          </div>

          <section className="desktop-overview">
            <div className="overview-card overview-card--hero">
              <div className="overview-title">Windows-style control room</div>
              <div className="overview-copy">
                Use the browser, terminal, file manager, and the Hermes/OpenClaw entry points from the same virtual machine.
                Everything points at the shared workspace mounted into Docker.
              </div>
              <div className="overview-actions">
                <button className="btn btn-primary" onClick={() => onOpenViewer('http://localhost:3010', 'Cloud Desktop', '#22c55e')}>Open VM</button>
                <button className="btn btn-ghost" onClick={() => onOpenViewer('http://localhost:9119', 'Hermes', '#aa3bff')}>Hermes</button>
                <button className="btn btn-ghost" onClick={() => onOpenViewer('http://localhost:18789', 'OpenClaw', '#f97316')}>OpenClaw</button>
              </div>
            </div>
            <div className="overview-card">
              <div className="overview-title">Desktop Access</div>
              <div className="overview-copy">Browser, terminal, and files are available directly inside the cloud desktop session.</div>
            </div>
          </section>

          {windows.map((win) => (
            <section key={win.id} className="desktop-window" style={{ left: win.x, top: win.y, width: win.w, height: win.h }}>
              <div className="desktop-window-bar">
                <div className="window-dots">
                  <span />
                  <span />
                  <span />
                </div>
                <span>{win.title}</span>
                <div className="window-actions">
                  <button onClick={() => updateWindow(win.id, { w: Math.max(260, win.w - 40), h: Math.max(220, win.h - 30) })}>-</button>
                  <button onClick={() => updateWindow(win.id, { w: win.w + 40, h: win.h + 30 })}>+</button>
                </div>
              </div>

              {win.kind === 'terminal' && (
                <div className="desktop-terminal">
                  <div className="terminal-toolbar">
                    <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="Type a shell command" />
                    <button className="btn btn-primary" onClick={runCommand}>Run</button>
                  </div>
                  <pre className="terminal-output">{output}</pre>
                </div>
              )}

              {win.kind === 'files' && (
                <div className="desktop-files">
                  <div className="files-path">{cwd}</div>
                  <div className="files-list">
                    {entries.map((entry) => (
                      <button
                        key={entry.path}
                        className="file-row"
                        onClick={() => entry.type === 'dir' ? fetchFiles(entry.path) : onOpenViewer(`file://${entry.path}`, entry.name, '#3b82f6')}
                      >
                        <span>{entry.type === 'dir' ? '📁' : '📄'}</span>
                        <span className="file-name">{entry.name}</span>
                        <span className="file-meta">{fmtBytes(entry.size)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {win.kind === 'browser' && (
                <div className="desktop-browser">
                  <div className="browser-toolbar">
                    <input
                      value={browserUrl}
                      onChange={(e) => setBrowserUrl(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          const next = normalizeBrowserUrl(browserUrl);
                          setBrowserCurrentUrl(next);
                          setBrowserUrl(next);
                        }
                      }}
                      placeholder="https://example.com or http://host.docker.internal:9119"
                    />
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        const next = normalizeBrowserUrl(browserUrl);
                        setBrowserCurrentUrl(next);
                        setBrowserUrl(next);
                      }}
                    >
                      Open
                    </button>
                    <button className="btn btn-ghost" onClick={() => onOpenViewer(browserCurrentUrl, browserCurrentUrl, '#22c55e')}>Pop Out</button>
                  </div>
                  <iframe
                    className="browser-frame"
                    src={browserCurrentUrl}
                    title="Browser preview"
                    allow="clipboard-read; clipboard-write; fullscreen"
                    referrerPolicy="no-referrer"
                  />
                  <div className="browser-hint">
                    This browser opens pages inside the desktop. If a site blocks embedding, use Pop Out to open it in the shared viewer.
                  </div>
                </div>
              )}
            </section>
          ))}
        </main>
      </section>

      <footer className="desktop-dock">
        <button className={`dock-item ${windowClasses.has('files') ? 'live' : ''}`} onClick={() => setWindows((wins) => [wins[0], ...wins.slice(1)])}>Files</button>
        <button className={`dock-item ${windowClasses.has('terminal') ? 'live' : ''}`} onClick={() => setWindows((wins) => [wins[1], wins[0], wins[2]])}>Terminal</button>
        <button className={`dock-item ${windowClasses.has('browser') ? 'live' : ''}`} onClick={() => setWindows((wins) => [wins[2], ...wins.slice(0, 2)])}>Browser</button>
        <button className="dock-item live" onClick={() => onOpenViewer('http://localhost:3010', 'Cloud Desktop', '#22c55e')}>VM</button>
        <button className="dock-item" onClick={() => onOpenViewer('http://localhost:9119', 'Hermes', '#aa3bff')}>Hermes</button>
        <button className="dock-item" onClick={() => onOpenViewer('http://localhost:18789', 'OpenClaw', '#f97316')}>OpenClaw</button>
      </footer>
    </div>
  );
}
