import { IconDocument, IconAlertTriangle, IconGauge, IconInfoCircle, IconCheckCircle, IconShield } from '../icons';
import { riskDisplay } from '../risk';

function StatTile({ label, value, icon: Icon, tone }) {
  return (
    <div className="stat-tile">
      <Icon size={16} className={`tone-${tone}`} />
      <div>
        <p className="stat-value">{value}</p>
        <p className="stat-label">{label}</p>
      </div>
    </div>
  );
}

export default function AnalysisOverview({ result }) {
  const count = result.anomalies_found;
  const ok = count === 0;
  const kindCount = new Set((result.anomalies || []).map((a) => a.title)).size;
  const fetchedCount = result.anomalies?.length ?? 0;
  const truncated = fetchedCount < count;
  const risk = riskDisplay(result.risk_level);

  const stats = [
    { label: 'Lines read', value: result.total_lines.toLocaleString(), icon: IconDocument, tone: 'neutral' },
    { label: 'Risk level', value: risk.label, icon: IconShield, tone: risk.tone },
    { label: 'Issues found', value: count.toLocaleString(), icon: IconAlertTriangle, tone: ok ? 'good' : 'critical' },
    { label: 'Anomaly rate', value: `${result.anomaly_rate}%`, icon: IconGauge, tone: ok ? 'good' : 'warning' },
  ];

  return (
    <div className="panel overview-card">
      <h2>Analysis overview</h2>

      <div className="overview-status">
        {ok
          ? <IconCheckCircle size={20} className="tone-good" />
          : <IconAlertTriangle size={20} className="tone-critical" />}
        <span className="overview-status-text">
          {ok ? 'Looks fine' : `${kindCount} kind${kindCount === 1 ? '' : 's'} of problem`}
        </span>
      </div>
      <p className="upload-subtitle">
        {ok
          ? "We didn't find anything unusual in this file."
          : count === kindCount
            ? 'See below for what happened and what to check.'
            : `Affecting ${count} sections of the file in total.`}
      </p>
      {truncated && (
        <p className="upload-subtitle">This file had a lot to check. Counts cover the first {fetchedCount}.</p>
      )}

      <div className="stat-tiles">
        {stats.map((s) => <StatTile key={s.label} {...s} />)}
      </div>

      {result.warnings?.length > 0 && (
        <div className="inline-notice">
          <IconInfoCircle size={15} className="tone-warning" />
          <div>
            {result.warnings.map((w, i) => <p key={i}>{w}</p>)}
          </div>
        </div>
      )}
    </div>
  );
}
