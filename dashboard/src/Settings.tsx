import { useState } from 'react';

interface Field { key: string; label: string; placeholder: string; type?: string; }

const HERMES_FIELDS: Field[] = [
  { key: 'HERMES_UID', label: 'Host UID', placeholder: 'e.g. 1000' },
  { key: 'HERMES_GID', label: 'Host GID', placeholder: 'e.g. 1000' },
  { key: 'API_SERVER_KEY', label: 'API Server Key', placeholder: 'optional — enables OpenAI-compat API', type: 'password' },
];

const OPENCLAW_FIELDS: Field[] = [
  { key: 'OPENCLAW_GATEWAY_TOKEN', label: 'Gateway Token', placeholder: 'auto-generated if blank', type: 'password' },
  { key: 'OPENCLAW_GATEWAY_PORT', label: 'Gateway Port', placeholder: '18789' },
  { key: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key', placeholder: 'sk-ant-…', type: 'password' },
  { key: 'OPENAI_API_KEY', label: 'OpenAI API Key', placeholder: 'sk-…', type: 'password' },
  { key: 'GEMINI_API_KEY', label: 'Gemini API Key', placeholder: 'AIza…', type: 'password' },
];

const CLOUD_FIELDS: Field[] = [
  { key: 'CLOUD_DESKTOP_PORT', label: 'Desktop Port', placeholder: '3010' },
  { key: 'CLOUD_DESKTOP_PUID', label: 'Desktop UID', placeholder: '1000' },
  { key: 'CLOUD_DESKTOP_PGID', label: 'Desktop GID', placeholder: '1000' },
];

function Section({ title, color, fields }: { title: string; color: string; fields: Field[] }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const save = () => {
    localStorage.setItem(`settings_${title}`, JSON.stringify(vals));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="settings-section">
      <div className="settings-section-title" style={{ borderColor: color }}>
        <span className="settings-dot" style={{ background: color }} />
        {title}
      </div>
      <div className="settings-fields">
        {fields.map(f => (
          <div key={f.key} className="settings-field">
            <label className="field-label">{f.label}</label>
            <input
              className="field-input"
              type={f.type || 'text'}
              placeholder={f.placeholder}
              value={vals[f.key] || ''}
              onChange={e => setVals(v => ({ ...v, [f.key]: e.target.value }))}
            />
            <span className="field-key">{f.key}</span>
          </div>
        ))}
      </div>
      <div className="settings-actions">
        <button className="btn btn-primary" style={{ background: color }} onClick={save}>
          {saved ? '✓ Saved' : 'Save'}
        </button>
        <span className="settings-note">
          Values are stored locally. Copy them into the respective <code>.env</code> file before launching.
        </span>
      </div>
    </div>
  );
}

export default function Settings() {
  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
        <p className="page-sub">Configure environment variables for each claw. Copy saved values into the claw's <code>.env</code> file.</p>
      </div>
      <Section title="Hermes Agent" color="#aa3bff" fields={HERMES_FIELDS} />
      <Section title="OpenClaw" color="#f97316" fields={OPENCLAW_FIELDS} />
      <Section title="Cloud Desktop" color="#22c55e" fields={CLOUD_FIELDS} />
    </div>
  );
}
