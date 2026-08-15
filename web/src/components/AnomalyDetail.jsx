import { useEffect, useState } from 'react';
import { getAnomaly } from '../api';

export default function AnomalyDetail({ runId, sessionId }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!sessionId) return;
    setDetail(null);
    setError(null);
    getAnomaly(runId, sessionId)
      .then(setDetail)
      .catch((err) => setError(err.message));
  }, [runId, sessionId]);

  if (!sessionId) {
    return (
      <div className="panel detail-panel empty-note">
        Select a session on the left to see why it was flagged.
      </div>
    );
  }

  if (error) {
    return <div className="panel detail-panel error-message">{error}</div>;
  }

  if (!detail) {
    return <div className="panel detail-panel">Loading…</div>;
  }

  return (
    <div className="panel detail-panel">
      <h3>Session {detail.session_id}</h3>
      <pre className="report-text">{detail.report}</pre>
    </div>
  );
}
