import { useRef, useState } from 'react';
import { IconUploadCloud, IconDocument, IconCheckCircle, IconX } from '../icons';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadZone({ onAnalyze, loading }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState(null);

  function pick(f) {
    if (f) setFile(f);
  }

  return (
    <div className="panel upload-card">
      <div className="upload-card-header">
        <IconUploadCloud size={20} />
        <div>
          <h2>Analyze a log file</h2>
          <p className="upload-subtitle">Upload a log file and we'll check it for problems.</p>
        </div>
      </div>

      <div
        className={`upload-zone${dragging ? ' dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        role="button"
        tabIndex={0}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".log,.txt"
          hidden
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <IconUploadCloud size={30} className="upload-zone-icon" />
        <p className="upload-title">Drag and drop your log file here</p>
        <p className="upload-hint">or</p>
        <button type="button" className="btn-secondary" onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}>
          Choose File
        </button>
      </div>

      {file && (
        <div className="file-chip">
          <IconDocument size={18} />
          <div className="file-chip-info">
            <span className="file-chip-name">{file.name}</span>
            <span className="file-chip-size">{formatSize(file.size)}</span>
          </div>
          <IconCheckCircle size={18} className="file-chip-check" />
          <button type="button" className="file-chip-remove" onClick={() => setFile(null)} aria-label="Remove file">
            <IconX size={16} />
          </button>
        </div>
      )}

      <button
        type="button"
        className="btn-primary analyze-btn"
        disabled={!file || loading}
        onClick={() => onAnalyze(file)}
      >
        {loading ? 'Analyzing…' : 'Analyze Log'}
      </button>
    </div>
  );
}
