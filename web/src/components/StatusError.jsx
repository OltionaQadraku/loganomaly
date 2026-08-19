import { useState } from 'react';
import { IconAlertCircle } from '../icons';

export default function StatusError({ error }) {
  const detail = error?.detail ?? {};
  const message = error?.message || 'Something went wrong.';
  const hasTechnicalDetails = detail.sample_lines?.length > 0 || detail.reason;
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="panel status-panel status-error">
      <span className="status-icon tone-critical"><IconAlertCircle size={20} /></span>
      <div>
        <p className="status-title">We couldn't check this file</p>
        <p className="status-message">{message}</p>

        {hasTechnicalDetails && (
          <>
            <button
              type="button"
              className="link-button"
              onClick={() => setShowDetails((v) => !v)}
            >
              {showDetails ? 'Hide technical details' : 'Show technical details'}
            </button>
            {showDetails && (
              <div className="technical-details">
                {detail.reason && <p className="tech-line">Reason code: {detail.reason}</p>}
                {typeof detail.skipped_lines === 'number' && (
                  <p className="tech-line">{detail.skipped_lines} line(s) were not understood.</p>
                )}
                {detail.sample_lines?.length > 0 && (
                  <pre className="sample-lines">{detail.sample_lines.join('\n')}</pre>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
