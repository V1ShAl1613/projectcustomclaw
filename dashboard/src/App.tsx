import { useState } from 'react';
import './App.css';
import Home from './Home';
import Dashboard from './Dashboard';
import Settings from './Settings';
import Viewer from './Viewer';
import Chat from './Chat';
import Desktop from './Desktop';

export type Page = 'desktop' | 'home' | 'chat' | 'dashboard' | 'settings' | 'viewer';

interface ViewerState { url: string; title: string; color: string; }

const NAV = [
  { id: 'desktop' as Page, label: 'Desktop', icon: '🖥️' },
  { id: 'chat' as Page, label: 'Chat', icon: '💬' },
  { id: 'home' as Page, label: 'Claws', icon: '🦀' },
  { id: 'dashboard' as Page, label: 'Dashboard', icon: '📊' },
  { id: 'settings' as Page, label: 'Settings', icon: '⚙️' },
];

export default function App() {
  const [page, setPage] = useState<Page>('desktop');
  const [viewer, setViewer] = useState<ViewerState | null>(null);

  const openViewer = (url: string, title: string, color: string) => {
    setViewer({ url, title, color });
    setPage('viewer');
  };

  const closeViewer = () => {
    setPage('home');
    setViewer(null);
  };

  return (
    <div className="app-shell">
      {page !== 'viewer' && (
        <aside className="sidebar">
          <div className="sidebar-brand">
            <span className="brand-icon">🦾</span>
            <span className="brand-name">CustomClaw</span>
          </div>
          <nav className="sidebar-nav">
            {NAV.map(n => (
              <button
                key={n.id}
                className={`nav-item ${page === n.id ? 'active' : ''}`}
                onClick={() => setPage(n.id)}
              >
                <span className="nav-icon">{n.icon}</span>
                <span>{n.label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-footer">v1.0.0</div>
        </aside>
      )}
      <main className={page === 'viewer' || page === 'chat' || page === 'desktop' ? 'main-content main-content--full' : 'main-content'}>
        {page === 'desktop' && <Desktop onNavigate={setPage} onOpenViewer={openViewer} />}
        {page === 'chat' && <Chat />}
        {page === 'home' && <Home onNavigate={setPage} />}
        {page === 'dashboard' && <Dashboard />}
        {page === 'settings' && <Settings />}
        {page === 'viewer' && viewer && (
          <Viewer url={viewer.url} title={viewer.title} color={viewer.color} onBack={closeViewer} />
        )}
      </main>
    </div>
  );
}
