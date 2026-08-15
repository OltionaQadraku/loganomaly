import { useState } from 'react';

const MODELS = [
  { value: 'pca', label: 'PCA' },
  { value: 'isolation_forest', label: 'Isolation Forest' },
  { value: 'lof', label: 'Local Outlier Factor' },
];

export default function UploadPanel({ onSubmit, loading }) {
  const [file, setFile] = useState(null);
  const [model, setModel] = useState('pca');

  function handleSubmit(e) {
    e.preventDefault();
    if (!file || loading) return;
    onSubmit(file, model);
  }

  return (
    <form className="panel upload-panel" onSubmit={handleSubmit}>
      <h2>Analyse a log file</h2>
      <div className="upload-row">
        <label className="field file-field">
          <span>Log file</span>
          <input
            type="file"
            accept=".log,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="field">
          <span>Model</span>
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {MODELS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!file || loading}>
          {loading ? 'Analysing…' : 'Analyse'}
        </button>
      </div>
      {file && <p className="file-name">{file.name}</p>}
    </form>
  );
}
