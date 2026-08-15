export default function AnomalyTable({ anomalies, selected, onSelect }) {
  if (!anomalies?.length) {
    return <p className="empty-note">No anomalies were flagged in this run.</p>;
  }

  return (
    <div className="panel anomaly-table-panel">
      <table className="anomaly-table">
        <thead>
          <tr>
            <th>Session</th>
            <th>Score</th>
            <th>Events</th>
            <th>Likely cause</th>
          </tr>
        </thead>
        <tbody>
          {anomalies.map((a) => (
            <tr
              key={a.session_id}
              className={selected === a.session_id ? 'selected' : ''}
              onClick={() => onSelect(a.session_id)}
            >
              <td>{a.session_id}</td>
              <td>{a.score}</td>
              <td>{a.event_count}</td>
              <td>{a.primary_cause.replace(/_/g, ' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
