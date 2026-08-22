import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import UploadZone from './components/UploadZone';
import StatusError from './components/StatusError';
import AnalysisOverview from './components/AnalysisOverview';
import IssueList from './components/IssueList';
import History from './components/History';
import Login from './components/Login';
import Register from './components/Register';
import { analyze, getMe, logout } from './api';
import './styles.css';

const PAGE_COPY = {
  analyze: {
    title: 'Analysis Results',
    subtitle: 'Upload a log file and we will find potential issues and explain what may have caused them. No technical knowledge needed.',
  },
  history: {
    title: 'History',
    subtitle: "Past files you've analyzed in this session.",
  },
};

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState(null);
  const [authView, setAuthView] = useState('login');

  const [view, setView] = useState('analyze');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getMe().then(setUser).finally(() => setAuthChecked(true));
  }, []);

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

  async function handleLogout() {
    await logout();
    setUser(null);
    setAuthView('login');
    setResult(null);
    setError(null);
    setView('analyze');
  }

  if (!authChecked) {
    return (
      <div className="auth-shell">
        <p className="status-message">Loading…</p>
      </div>
    );
  }

  if (!user) {
    return authView === 'login'
      ? <Login onLoggedIn={setUser} onSwitchToRegister={() => setAuthView('register')} />
      : <Register onLoggedIn={setUser} onSwitchToLogin={() => setAuthView('login')} />;
  }

  const copy = PAGE_COPY[view];

  return (
    <div className="shell">
      <Sidebar view={view} onNavigate={setView} user={user} onLogout={handleLogout} />

      <main className="main">
        <header className="page-header">
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </header>

        {view === 'analyze' ? (
          <>
            <div className={`top-grid${error || result ? '' : ' single'}`}>
              <UploadZone onAnalyze={handleAnalyze} loading={loading} />
              {error
                ? <StatusError error={error} />
                : result && <AnalysisOverview result={result} />}
            </div>

            {result && <IssueList anomalies={result.anomalies} runId={result.run_id} />}
          </>
        ) : (
          <History />
        )}
      </main>
    </div>
  );
}
