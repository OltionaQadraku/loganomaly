const API_BASE = 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, detail) {
    super(message);
    this.name = 'ApiError';
    this.detail = detail || {};
  }
}

export async function analyze(file, model, top = 20) {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(
    `${API_BASE}/api/analyze?model=${encodeURIComponent(model)}&top=${top}`,
    { method: 'POST', body: form }
  );

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
  const res = await fetch(`${API_BASE}/api/runs/${runId}/anomalies/${sessionId}`);
  if (!res.ok) {
    throw new Error('Could not load the details for this session.');
  }
  return res.json();
}
