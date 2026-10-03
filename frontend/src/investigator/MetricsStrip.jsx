import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function MetricsStrip() {
  const [m, setM] = useState(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await api("/v1/metrics");
        if (alive) setM(data);
      } catch {
        if (alive) setM(null);
      }
    }
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (!m) return null;
  const tc = m.tier_counts || {};
  const lat = m.latency_ms || {};

  return (
    <div className="metrics">
      <div><small>requests</small><b>{m.requests}</b></div>
      <div><small>low</small><b>{tc.low}</b></div>
      <div><small>medium</small><b>{tc.medium}</b></div>
      <div><small>high</small><b>{tc.high}</b></div>
      <div><small>extreme</small><b>{tc.extreme}</b></div>
      <div><small>p95 latency (ms)</small><b>{lat.p95}</b></div>
      <div><small>open cases</small><b>{m.open_cases}</b></div>
    </div>
  );
}
