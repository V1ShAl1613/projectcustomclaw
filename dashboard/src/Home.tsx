import { useEffect, useRef, useState } from 'react';
import type { Page } from './App';

const API = 'http://localhost:3001';

interface Container { name: string; running: boolean; status: string; image: string; }
interface Claw {
  id: string; name: string; description: string; color: string;
  url: string; isRunning: boolean; containers: Container[];
}

export default function Home({ onNavigate }: {
  onNavigate: (p: Page) => void;
}) {
  const [claws, setClaws] = useState<Claw[]>([]);
  const [apiOk, setApiOk] = useState(true);
  const [loading, setLoading] = useState<Record<string, 'launching' | 'stopping' | null>>({});
  const [elapsed, setElapsed] = useState<Record<string, number>>({});
  const [error, setError] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [showLogs, setShowLogs] = useState<Record<string, boolean>>({});
  const timers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const fetchClaws = () =>
    fetch(`${API}/api/claws`)
      .then(r => r.json())
      .then(d => { setClaws(d); setApiOk(true); })
      .catch(() => setApiOk(false));

  useEffect(() => {
    fetchClaws();
    const t = setInterval(fetchClaws, 4000);
    return () => clearInterval(t);
  }, []);

  const startTimer = (id: string) => {
    setElapsed(e => ({ ...e, [id]: 0 }));
    timers.current[id] = setInterval(() => {
      setElapsed(e => ({ ...e, [id]: (e[id] || 0) + 1 }));
    }, 1000);
  };

  const stopTimer = (id: string) => {
    clearInterval(timers.current[id]);
    setElapsed(e => ({ ...e, [id]: 0 }));
  };

  const launch = async (id: string) => {
    setLoading(l => ({ ...l, [id]: 'launching' }));
    setError(e => ({ ...e, [id]: '' }));
    startTimer(id);
    try {
      const res = await fetch(`${API}/api/launch/${id}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setError(e => ({ ...e, [id]: data.error || 'Launch failed' }));
      } else {
        await fetchClaws();
      }
    } catch {
      setError(e => ({ ...e, [id]: 'Cannot reach API server on localhost:3001. Run: npm run server' }));
    }
    stopTimer(id);
    setLoading(l => ({ ...l, [id]: null }));
  };

  const stop = async (id: string) => {
    setLoading(l => ({ ...l, [id]: 'stopping' }));
    try {
      await fetch(`${API}/api/stop/${id}`, { method: 'POST' });
      await fetchClaws();
    } catch {}
    setLoading(l => ({ ...l, [id]: null }));
  };

  const toggleLogs = async (id: string) => {
    if (showLogs[id]) { setShowLogs(s => ({ ...s, [id]: false })); return; }
    const data = await fetch(`${API}/api/logs/${id}`).then(r => r.json()).catch(() => ({ logs: '' }));
    setLogs(l => ({ ...l, [id]: data.logs }));
    setShowLogs(s => ({ ...s, [id]: true }));
  };

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  return (
    <div className="page">
      <div className="page-header">
        <h1 style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>START YOUR JOURNEY</h1>
        <p className="page-sub">Select an agent to launch. First launch builds the Docker image — this can take 5–15 minutes.</p>
      </div>

      {!apiOk && (
        <div className="alert-banner">
          ⚠️ API server not reachable at <code>localhost:3001</code> — run <code>npm run server</code> in the dashboard folder.
        </div>
      )}

      <div className="claw-grid">
        {claws.map(claw => {
          const isLaunching = loading[claw.id] === 'launching';
          const isStopping = loading[claw.id] === 'stopping';
          const secs = elapsed[claw.id] || 0;

          return (
            <div
              key={claw.id}
              className={`claw-card ${claw.isRunning ? 'running' : ''}`}
              style={{ '--accent': claw.color } as React.CSSProperties}
            >
              <div className="claw-card-header">
                <div className="claw-title-row">
                  <span className="claw-dot" style={{ background: claw.isRunning ? '#22c55e' : '#6b7280' }} />
                  <h2 className="claw-name">{claw.name}</h2>
                  <span className={`claw-badge ${claw.isRunning ? 'badge-running' : 'badge-stopped'}`}>
                    {claw.isRunning ? 'Running' : 'Stopped'}
                  </span>
                </div>
                <p className="claw-desc">{claw.description}</p>
              </div>

              <div className="claw-containers">
                {claw.containers.map(c => (
                  <div key={c.name} className="container-row">
                    <span className={`container-dot ${c.running ? 'dot-green' : 'dot-gray'}`} />
                    <span className="container-name">{c.name}</span>
                    <span className="container-status">{c.status}</span>
                  </div>
                ))}
              </div>

              {isLaunching && (
                <div className="launch-progress">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ background: claw.color }} />
                  </div>
                  <span className="progress-label">
                    Building &amp; starting… {secs > 0 && <span className="progress-time">{fmtTime(secs)}</span>}
                    {secs > 30 && <span className="progress-hint"> — Docker image build in progress, please wait</span>}
                  </span>
                </div>
              )}

              {error[claw.id] && (
                <div className="claw-error">
                  <strong>Error:</strong> {error[claw.id]}
                </div>
              )}

              <div className="claw-actions">
                {claw.isRunning ? (
                  <>
                    <button className="btn btn-primary" style={{ background: claw.color }} onClick={() => window.open(claw.url, '_blank')}>Open {claw.name}</button>
                    <button className="btn btn-ghost" onClick={() => toggleLogs(claw.id)}>
                      {showLogs[claw.id] ? 'Hide Logs' : 'View Logs'}
                    </button>
                    <button className="btn btn-danger" onClick={() => stop(claw.id)} disabled={!!loading[claw.id]}>
                      {isStopping ? <><span className="spinner" /> Stopping…</> : 'Stop'}
                    </button>
                    <button className="btn btn-ghost" onClick={() => onNavigate('dashboard')}>Dashboard →</button>
                  </>
                ) : (
                  <button
                    className="btn btn-primary"
                    style={{ background: claw.color }}
                    onClick={() => launch(claw.id)}
                    disabled={isLaunching}
                  >
                    {isLaunching
                      ? <><span className="spinner" /> Launching… {secs > 0 && `(${fmtTime(secs)})`}</>
                      : `Launch ${claw.name}`}
                  </button>
                )}
              </div>

              {showLogs[claw.id] && (
                <pre className="log-box">{logs[claw.id] || 'No logs yet.'}</pre>
              )}
            </div>
          );
        })}

        {claws.length === 0 && apiOk && (
          <div className="empty-state">
            <p>Loading claws…</p>
          </div>
        )}
      </div>
    </div>
  );
}
