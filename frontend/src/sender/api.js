const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(status) { super(String(status)); this.status = status; }
}

async function req(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch { throw new ApiError(0); }
  if (!res.ok) throw new ApiError(res.status);
  return res.json();
}

export const api = {
  examples: () => req('/v1/demo/examples'),
  load: (id) => req(`/v1/demo/load/${id}`, { method: 'POST' }),
  score: (b) => req('/v1/score', { method: 'POST', body: b }),
  confirm: (tx_ref, decision) => req('/v1/confirm', { method: 'POST', body: { tx_ref, decision } }),
  report: (b) => req('/v1/report', { method: 'POST', body: b }),
  transfer: (ref) => req(`/v1/transfers/${ref}`),
};

export function friendly(err, t) {
  if (err.status === 409) return t.e409;
  if (err.status === 403) return t.e403;
  return t.eNet;
}