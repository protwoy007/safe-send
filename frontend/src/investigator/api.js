const BASE = import.meta.env.VITE_API_URL ?? "";

export async function api(path, { key, method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(key ? { "X-API-Key": key } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Service unavailable, please try again.");
  }
  if (res.status === 401) throw new Error("Invalid key.");
  if (!res.ok) throw new Error("Something went wrong. Please try again.");
  return res.json();
}
