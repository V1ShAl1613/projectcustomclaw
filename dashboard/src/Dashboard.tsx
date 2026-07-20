import { useEffect, useState } from 'react';

const API = 'http://localhost:3001';

interface Container { name: string; running: boolean; status: string; image: string; }
interface Claw { id: string; name: string; color: string; url: string; isRunning: boolean; containers: Container[]; }

export default function Dashboard() {
  const [claws, setClaws] = useState<Claw[]>([]);
  const [lastUpdated, setLastUpdated] = useState('');

  const fetch_ = () =>
    fetch(`${API}/api/claws`).then(r => r.json()).then(d => {
      setClaws(d);
      setLastUpdated(new Date().toLocaleTimeString());
    }).catch(() => {});

  useEffect(() => {
    fetch_();
    const t = setInterval(fetch_, 5000);
    return () => clearInterval(t);
  }, []);

  const totalRunning = claws.reduce((n, c) => n + c.containers.filter(x => x.running).length, 0);
  const totalContainers = claws.reduce((n, c) => n + c.containers.length, 0);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="page-sub">Live agent status · refreshes every 5s · last updated {lastUpdated}</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-value">{claws.length}</div>
          <div className="stat-label">Total Claws</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#22c55e' }}>{claws.filter(c => c.isRunning).length}</div>
          <div className="stat-label">Running</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{totalRunning}/{totalContainers}</div>
          <div className="stat-label">Containers Up</div>
        </div>
      </div>

      <div className="agent-table-wrap">
        <table className="agent-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Container</th>
              <th>Status</th>
              <th>Image</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {claws.flatMap(claw =>
              claw.containers.map((c, i) => (
                <tr key={c.name} className={c.running ? 'row-running' : 'row-stopped'}>
                  {i === 0 && (
                    <td rowSpan={claw.containers.length} className="agent-name-cell">
                      <span className="agent-dot" style={{ background: claw.color }} />
                      {claw.name}
                    </td>
                  )}
                  <td><code>{c.name}</code></td>
                  <td>
                    <span className={`status-pill ${c.running ? 'pill-green' : 'pill-gray'}`}>
                      {c.running ? '● ' : '○ '}{c.status}
                    </span>
                  </td>
                  <td className="image-cell">{c.image}</td>
                  {i === 0 && (
                    <td rowSpan={claw.containers.length}>
                      {claw.isRunning
                        ? <a href={claw.url} target="_blank" rel="noreferrer" className="table-link">Open ↗</a>
                        : <span className="table-na">—</span>}
                    </td>
                  )}
                </tr>
              ))
            )}
            {claws.length === 0 && (
              <tr><td colSpan={5} className="empty-row">No data — is the API server running?</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
