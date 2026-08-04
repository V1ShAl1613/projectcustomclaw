interface ViewerProps {
  url: string;
  title: string;
  color: string;
  onBack: () => void;
}

export default function Viewer({ url, title, color, onBack }: ViewerProps) {
  return (
    <div className="viewer-shell">
      <div className="viewer-bar" style={{ borderBottomColor: color }}>
        <button className="viewer-back" onClick={onBack}>← Back</button>
        <span className="viewer-title" style={{ color }}>{title}</span>
        <span className="viewer-url">{url}</span>
        <a className="btn btn-outline viewer-external" href={url} target="_blank" rel="noreferrer">↗ Open tab</a>
      </div>
      <iframe
        className="viewer-frame"
        src={url}
        title={title}
        allow="clipboard-read; clipboard-write; fullscreen; pointer-lock"
      />
    </div>
  );
}
