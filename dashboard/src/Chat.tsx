import { useEffect, useState, useRef } from 'react';

const API = 'http://localhost:3001';

interface Container { name: string; running: boolean; status: string; image: string; }
interface Claw {
  id: string; name: string; description: string; color: string;
  url: string; isRunning: boolean; containers: Container[];
}

export default function Chat() {
  const [claws, setClaws] = useState<Claw[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [elapsed, setElapsed] = useState<number>(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchClaws = () =>
    fetch(`${API}/api/claws`)
      .then(r => r.json())
      .then(d => setClaws(d))
      .catch(() => {});

  useEffect(() => {
    fetchClaws();
    const t = setInterval(fetchClaws, 4000);
    return () => clearInterval(t);
  }, []);

  const selectedClaw = claws.find(c => c.id === selectedId);

  useEffect(() => {
    if (selectedClaw && !selectedClaw.isRunning && !loading) {
      launch(selectedClaw.id);
    }
  }, [selectedClaw, loading]);

  const launch = async (id: string) => {
    setLoading(true);
    setError('');
    setElapsed(0);
    
    timer.current = setInterval(() => {
      setElapsed(e => e + 1);
    }, 1000);

    try {
      const res = await fetch(`${API}/api/launch/${id}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || 'Launch failed');
      } else {
        await fetchClaws();
      }
    } catch {
      setError('Cannot reach API server on localhost:3001. Run: npm run server');
    }

    if (timer.current) clearInterval(timer.current);
    setLoading(false);
  };

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  return (
    <div className="chat-layout">
      <div className="chat-sidebar">
        <h2 className="chat-sidebar-title">Select a Claw</h2>
        <div className="chat-claw-list">
          {claws.map(claw => (
            <button
              key={claw.id}
              className={`chat-claw-btn ${selectedId === claw.id ? 'active' : ''}`}
              style={{ '--accent': claw.color } as React.CSSProperties}
              onClick={() => setSelectedId(claw.id)}
            >
              <span className="claw-dot" style={{ background: claw.isRunning ? '#22c55e' : '#6b7280' }} />
              <span className="chat-claw-name">{claw.name}</span>
            </button>
          ))}
          {claws.length === 0 && <div className="chat-empty-msg">No claws found.</div>}
        </div>
      </div>
      
      <div className="chat-main">
        {!selectedClaw ? (
          <div className="chat-placeholder">
            <span className="chat-placeholder-icon">🤖</span>
            <p>Select a claw to start chatting.</p>
          </div>
        ) : error ? (
          <div className="chat-error-state">
            <span className="chat-error-icon">⚠️</span>
            <h3>Error launching {selectedClaw.name}</h3>
            <p>{error}</p>
            <button className="btn btn-primary" onClick={() => launch(selectedClaw.id)}>Retry</button>
          </div>
        ) : !selectedClaw.isRunning || loading ? (
          <div className="chat-loading-state">
            <div className="spinner-large" style={{ borderColor: `${selectedClaw.color} transparent transparent transparent` }}></div>
            <h3>Waking up {selectedClaw.name}…</h3>
            <p className="chat-loading-time">{elapsed > 0 ? fmtTime(elapsed) : ''}</p>
            {elapsed > 15 && <p className="chat-hint">Building docker image. This might take a few minutes the first time.</p>}
          </div>
        ) : (
          <iframe
            className="chat-frame"
            src={selectedClaw.url}
            title={selectedClaw.name}
            allow="clipboard-read; clipboard-write"
          />
        )}
      </div>
    </div>
  );
}
