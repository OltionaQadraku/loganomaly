const API_BASE = 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, detail) {
    super(message);
    this.name = 'ApiError';
    this.detail = detail || {};
  }
}
const MAX_ANOMALIES_FETCHED = 500;

export async function analyze(file) {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${API_BASE}/api/analyze?top=${MAX_ANOMALIES_FETCHED}`, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === 'object') {
      throw new ApiError(detail.message || 'The upload failed.', detail);
    }
    throw new ApiError(typeof detail === 'string' ? detail : 'The upload failed.', {});
  }

  return res.json();
}

export async function getAnomaly(runId, sessionId) {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/anomalies/${encodeURIComponent(sessionId)}`);
  if (!res.ok) {
    throw new Error('Could not load the details for this item.');
  }
  return res.json();
}
