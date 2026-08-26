const API_BASE = 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, detail) {
    super(message);
    this.name = 'ApiError';
    this.detail = detail || {};
  }
}

async function throwApiError(res, fallback) {
  const body = await res.json().catch(() => null);
  const detail = body?.detail;
  if (detail && typeof detail === 'object') {
    throw new ApiError(detail.message || fallback, detail);
  }
  throw new ApiError(typeof detail === 'string' ? detail : fallback, {});
}

const MAX_ANOMALIES_FETCHED = 500;

export async function analyze(file) {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${API_BASE}/api/analyze?top=${MAX_ANOMALIES_FETCHED}`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });

  if (!res.ok) await throwApiError(res, 'The upload failed.');
  return res.json();
}

export async function getAnomaly(runId, sessionId) {
  const res = await fetch(
    `${API_BASE}/api/runs/${runId}/anomalies/${encodeURIComponent(sessionId)}`,
    { credentials: 'include' },
  );
  if (!res.ok) {
    throw new Error('Could not load the details for this item.');
  }
  return res.json();
}

export async function explainAnomaly(runId, sessionId) {
  const res = await fetch(
    `${API_BASE}/api/runs/${runId}/anomalies/${encodeURIComponent(sessionId)}/explain`,
    { method: 'POST', credentials: 'include' },
  );
  if (!res.ok) await throwApiError(res, "Couldn't get a more detailed explanation.");
  return res.json();
}

export async function listRuns() {
  const res = await fetch(`${API_BASE}/api/runs`, { credentials: 'include' });
  if (!res.ok) {
    throw new Error('Could not load past analyses.');
  }
  return res.json();
}

export async function getRun(runId) {
  const res = await fetch(`${API_BASE}/api/runs/${runId}`, { credentials: 'include' });
  if (!res.ok) {
    throw new Error('Could not load that analysis.');
  }
  return res.json();
}

export async function register(username, password) {
  const res = await fetch(`${API_BASE}/api/register`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) await throwApiError(res, 'Could not create your account.');
  return res.json();
}

export async function login(username, password) {
  const res = await fetch(`${API_BASE}/api/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) await throwApiError(res, 'Could not log you in.');
  return res.json();
}

export async function logout() {
  await fetch(`${API_BASE}/api/logout`, { method: 'POST', credentials: 'include' });
}

export async function getMe() {
  const res = await fetch(`${API_BASE}/api/me`, { credentials: 'include' });
  if (!res.ok) return null;
  return res.json();
}
