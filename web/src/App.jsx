import { useState } from 'react';
import UploadPanel from './components/UploadPanel';
import ErrorPanel from './components/ErrorPanel';
import WarningsPanel from './components/WarningsPanel';
import SummaryPanel from './components/SummaryPanel';
import AnomalyTable from './components/AnomalyTable';
import AnomalyDetail from './components/AnomalyDetail';
import { analyze } from './api';
import './styles.css';

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  async function handleSubmit(file, model) {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelected(null);
    try {
      const data = await analyze(file, model);
      setResult(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>LogSense</h1>
        <p>Detecting and explaining anomalies in log files.</p>
      </header>

      <UploadPanel onSubmit={handleSubmit} loading={loading} />

      {error && <ErrorPanel error={error} />}

      {result && (
        <>
          <WarningsPanel warnings={result.warnings} />
          <SummaryPanel result={result} />
          <div className="results-columns">
            <AnomalyTable
              anomalies={result.anomalies}
              selected={selected}
              onSelect={setSelected}
            />
            <AnomalyDetail runId={result.run_id} sessionId={selected} />
          </div>
        </>
      )}
    </div>
  );
}
