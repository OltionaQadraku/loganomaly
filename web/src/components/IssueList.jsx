import { useState } from 'react';
import { getAnomaly } from '../api';
import { parseReport } from '../reportFormat';
import { IconAlertCircle, IconAlertTriangle, IconInfoCircle, IconChevronDown } from '../icons';

const SEVERITY_ICON = {
  CRITICAL: IconAlertCircle,
  HIGH: IconAlertCircle,
  MEDIUM: IconAlertTriangle,
  LOW: IconInfoCircle,
};

function IssueDetails({ report }) {
  const sections = parseReport(report);
  if (!sections) return null;

  return (
    <div className="issue-details">
      {sections.why.length > 0 && (
        <div className="issue-section">
          <h4>Why we think so</h4>
          <ul>
            {sections.why.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </div>
      )}
      {sections.means && (
        <div className="issue-section">
          <h4>What this usually means</h4>
          <p>{sections.means}</p>
        </div>
      )}
      {sections.check && (
        <div className="issue-section">
          <h4>What to check</h4>
          <p>{sections.check}</p>
        </div>
      )}
    </div>
  );
}

function groupByTitle(anomalies) {
  const groups = new Map();
  for (const a of anomalies) {
    const key = a.title;
    if (!groups.has(key)) {
      groups.set(key, { title: a.title, severity: a.severity, examples: [] });
    }
    groups.get(key).examples.push(a);
  }
  const severityRank = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  return Array.from(groups.values()).sort((a, b) => {
    const rankDiff = (severityRank[a.severity] ?? 9) - (severityRank[b.severity] ?? 9);
    return rankDiff !== 0 ? rankDiff : b.examples.length - a.examples.length;
  });
}

export default function IssueList({ anomalies, runId }) {
  const [openTitle, setOpenTitle] = useState(null);
  const [details, setDetails] = useState({});

  if (!anomalies?.length) return null;

  const groups = groupByTitle(anomalies);
  const total = anomalies.length;

  function toggle(group) {
    if (openTitle === group.title) {
      setOpenTitle(null);
      return;
    }
    setOpenTitle(group.title);
    const representative = group.examples[0];
    if (!details[group.title]) {
      getAnomaly(runId, representative.session_id)
        .then((full) => setDetails((prev) => ({ ...prev, [group.title]: full })))
        .catch(() => setDetails((prev) => ({ ...prev, [group.title]: { error: true } })));
    }
  }

  return (
    <div className="panel issues-panel">
      <div className="panel-heading">
        <h2>Possible issues</h2>
        <p className="upload-subtitle">Grouped by type and ranked by severity.</p>
      </div>

      <div className="issue-list">
        {groups.map((group) => {
          const isOpen = openTitle === group.title;
          const detail = details[group.title];
          const count = group.examples.length;
          const share = Math.round((count / total) * 100);
          const Icon = SEVERITY_ICON[group.severity] || IconInfoCircle;

          return (
            <div key={group.title} className={`issue-row${isOpen ? ' open' : ''}`}>
              <button type="button" className="issue-summary" onClick={() => toggle(group)}>
                <span className={`issue-icon tone-${group.severity?.toLowerCase()}`}>
                  <Icon size={18} />
                </span>
                <span className="issue-main">
                  <span className="issue-title-row">
                    <span className="issue-title">{group.title}</span>
                    <span className="issue-count">
                      {count === 1 ? 'found in 1 section' : `found in ${count} sections`}
                    </span>
                  </span>
                  <span className="issue-bar-track">
                    <span
                      className={`issue-bar-fill tone-${group.severity?.toLowerCase()}`}
                      style={{ width: `${Math.max(share, 4)}%` }}
                    />
                  </span>
                </span>
                <IconChevronDown size={18} className={`issue-chevron${isOpen ? ' rotated' : ''}`} />
              </button>
              {isOpen && (
                <div className="issue-body">
                  {!detail && <p className="status-message">Loading details…</p>}
                  {detail?.error && <p className="status-message">Couldn't load the details for this item.</p>}
                  {detail && !detail.error && <IssueDetails report={detail.report} />}
                  {count > 1 && (
                    <p className="issue-note">
                      Showing one example — the same kind of issue happened {count} times in this file.
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
