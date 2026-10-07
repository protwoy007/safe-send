const BASE = import.meta.env.VITE_API_URL ?? "";

export async function getImpact(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== "" && v != null) qs.set(k, v);
  });
  const q = qs.toString();
  let res;
  try {
    res = await fetch(`${BASE}/v1/impact${q ? `?${q}` : ""}`);
  } catch {
    const e = new Error("net"); e.status = 0; throw e;
  }
  if (!res.ok) { const e = new Error("http"); e.status = res.status; throw e; }
  return res.json();
}

export function impactError(err) {
  if (err.status === 429) return "Too many requests, wait a minute.";
  if (err.status === 422) return "One of the values is not valid.";
  return "Service unavailable, please try again.";
}
