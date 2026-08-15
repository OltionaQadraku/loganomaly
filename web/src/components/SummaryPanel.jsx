function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function SummaryPanel({ result }) {
  const causes = Object.entries(result.cause_distribution || {});

  return (
    <div className="panel summary-panel">
      <div className="stat-grid">
        <Stat label="Sessions analysed" value={result.total_sessions} />
        <Stat label="Anomalies found" value={result.anomalies_found} />
        <Stat label="Anomaly rate" value={`${result.anomaly_rate}%`} />
        <Stat label="Lines parsed" value={result.total_lines} />
      </div>

      {causes.length > 0 && (
        <div className="cause-list">
          <h3>Likely causes</h3>
          <ul>
            {causes.map(([cause, count]) => (
              <li key={cause}>
                <span className="cause-name">{cause.replace(/_/g, ' ')}</span>
                <span className="cause-count">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
