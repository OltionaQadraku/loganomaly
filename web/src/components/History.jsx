import { useEffect, useMemo, useState } from 'react';
import { listRuns, getRun } from '../api';
import AnalysisOverview from './AnalysisOverview';
import IssueList from './IssueList';
import { riskDisplay } from '../risk';
import { IconDocument, IconAlertTriangle, IconCheckCircle } from '../icons';

const PAGE_SIZE = 6;
const RISK_FILTERS = ['All', 'None', 'Low', 'Medium', 'High', 'Critical'];
const SORTS = {
  newest: { label: 'Newest first', fn: (a, b) => new Date(b.analyzed_at) - new Date(a.analyzed_at) },
  oldest: { label: 'Oldest first', fn: (a, b) => new Date(a.analyzed_at) - new Date(b.analyzed_at) },
  risk: { label: 'Highest risk first', fn: (a, b) => b.anomaly_rate - a.anomaly_rate },
  issues: { label: 'Most issues first', fn: (a, b) => b.anomalies_found - a.anomalies_found },
};

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return {
      date: d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }),
      time: d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }),
    };
  } catch {
    return { date: iso, time: '' };
  }
}

function formatDuration(seconds) {
  if (typeof seconds !== 'number') return null;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(seconds < 10 ? 2 : 0);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(seconds < 10 ? 5 : 2, '0')}`;
}

function ScoreRing({ value, tone }) {
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value));
  const offset = circumference * (1 - pct / 100);
  return (
    <svg width="50" height="50" viewBox="0 0 50 50" className="score-ring">
      <circle cx="25" cy="25" r={radius} className="score-ring-track" />
      <circle
        cx="25" cy="25" r={radius}
        className={`score-ring-fill tone-${tone}`}
        style={{ strokeDasharray: circumference, strokeDashoffset: offset }}
        transform="rotate(-90 25 25)"
      />
      <text x="25" y="29" textAnchor="middle" className="score-ring-text">{Math.round(pct)}</text>
    </svg>
  );
}

export default function History() {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loadingRun, setLoadingRun] = useState(false);

  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('All');
  const [sortKey, setSortKey] = useState('newest');
  const [page, setPage] = useState(1);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err) => setError(err.message));
  }, []);

  function openRun(runId) {
    setLoadingRun(true);
    getRun(runId)
      .then(setSelected)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingRun(false));
  }

  const filtered = useMemo(() => {
    if (!runs) return [];
    return runs
      .filter((r) => r.filename.toLowerCase().includes(search.toLowerCase()))
      .filter((r) => riskFilter === 'All' || riskDisplay(r.risk_level).label === riskFilter)
      .sort(SORTS[sortKey].fn);
  }, [runs, search, riskFilter, sortKey]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (selected) {
    return (
      <>
        <button type="button" className="link-button back-link" onClick={() => setSelected(null)}>
          ← Back to history
        </button>
        <AnalysisOverview result={selected} />
        <IssueList anomalies={selected.anomalies} runId={selected.run_id} meta={selected} />
      </>
    );
  }

  return (
    <div className="panel">
      <div className="history-toolbar">
        <input
          type="text"
          className="history-search"
          placeholder="Search by filename…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
        <select
          className="history-select"
          value={riskFilter}
          onChange={(e) => { setRiskFilter(e.target.value); setPage(1); }}
        >
          {RISK_FILTERS.map((r) => <option key={r} value={r}>{r === 'All' ? 'All risk levels' : r}</option>)}
        </select>
        <select
          className="history-select"
          value={sortKey}
          onChange={(e) => { setSortKey(e.target.value); setPage(1); }}
        >
          {Object.entries(SORTS).map(([key, { label }]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </div>

      {loadingRun && <p className="status-message">Loading…</p>}
      {error && <p className="status-message">{error}</p>}
      {!runs && !error && <p className="status-message">Loading…</p>}
      {runs?.length === 0 && (
        <p className="status-message">No analyses yet. Upload a file to get started.</p>
      )}
      {runs?.length > 0 && filtered.length === 0 && (
        <p className="status-message">No analyses match your search/filter.</p>
      )}

      {pageRows.length > 0 && (
        <div className="history-table">
          <div className="history-head-row">
            <span>Analyzed on</span>
            <span>Summary</span>
            <span>Score</span>
            <span>Actions</span>
          </div>

          {pageRows.map((run) => {
            const { date, time } = formatDate(run.analyzed_at);
            const duration = formatDuration(run.duration_seconds);
            const risk = riskDisplay(run.risk_level);
            const kindCount = Object.keys(run.cause_distribution || {}).length;
            const ok = run.anomalies_found === 0;

            return (
              <div key={run.run_id} className="history-table-row">
                <div className="history-cell history-cell-date">
                  <span className="mobile-label">Analyzed on</span>
                  <span>{date}</span>
                  <span className="history-cell-sub">{time}</span>
                  {duration && <span className="history-cell-sub">Took {duration}</span>}
                </div>

                <div className="history-cell">
                  <span className="mobile-label">Summary</span>
                  <span className="history-filename" title={run.filename}>{run.filename}</span>
                  <div className="history-summary-line">
                    {ok
                      ? <IconCheckCircle size={16} className="tone-good" />
                      : <IconAlertTriangle size={16} className={`tone-${risk.tone}`} />}
                    <span className="history-summary-title">
                      {ok ? 'No problems detected' : `${kindCount} kind${kindCount === 1 ? '' : 's'} of problem`}
                    </span>
                  </div>
                  <span className="history-cell-sub">
                    {ok ? 'Everything looks good' : `${run.anomalies_found} issues found · ${risk.label} risk`}
                  </span>
                  <div className="history-badges">
                    <span className="history-badge">{run.total_lines.toLocaleString()} lines</span>
                    <span className={`history-badge tone-bg-${risk.tone}`}>{run.anomaly_rate}% anomaly rate</span>
                  </div>
                </div>

                <div className="history-cell history-cell-score">
                  <span className="mobile-label">Score</span>
                  <ScoreRing value={run.anomaly_rate} tone={risk.tone} />
                  <span className={`history-cell-sub tone-${risk.tone}`}>{risk.label}</span>
                </div>

                <div className="history-cell">
                  <span className="mobile-label">Actions</span>
                  <button type="button" className="btn-secondary" onClick={() => openRun(run.run_id)}>
                    <IconDocument size={14} />
                    View results
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {filtered.length > PAGE_SIZE && (
        <div className="history-pagination">
          <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Prev
          </button>
          <span className="history-cell-sub">Page {page} of {pageCount}</span>
          <button type="button" className="btn-secondary" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
