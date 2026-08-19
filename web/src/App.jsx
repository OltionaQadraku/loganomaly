import { useState } from 'react';
import Sidebar from './components/Sidebar';
import UploadZone from './components/UploadZone';
import StatusError from './components/StatusError';
import AnalysisOverview from './components/AnalysisOverview';
import IssueList from './components/IssueList';
import { analyze } from './api';
import './styles.css';

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleAnalyze(file) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await analyze(file);
      setResult(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="shell">
      <Sidebar />

      <main className="main">
        <header className="page-header">
          <h1>Analysis Results</h1>
          <p>Upload a log file and we will find potential issues and explain what may have caused them. No technical knowledge needed.</p>
        </header>

        <div className={`top-grid${error || result ? '' : ' single'}`}>
          <UploadZone onAnalyze={handleAnalyze} loading={loading} />
          {error
            ? <StatusError error={error} />
            : result && <AnalysisOverview result={result} />}
        </div>

        {result && <IssueList anomalies={result.anomalies} runId={result.run_id} />}
      </main>
    </div>
  );
}
