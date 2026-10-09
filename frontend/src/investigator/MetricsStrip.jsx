import { useEffect, useState } from "react";
import { api } from "./api.js";
import Icon from "../ui/icons.jsx";

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
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!m) return null;
  const tc = m.tier_counts || {};
  const lat = m.latency_ms || {};
  const kpis = [
    { label: "Requests", value: m.requests, icon: "send", tone: "teal" },
    { label: "Open cases", value: m.open_cases, icon: "clock", tone: "extreme" },
    { label: "p95 latency", value: lat.p95, unit: "ms", icon: "trend", tone: "teal" },
    { label: "Reports", value: m.reports ?? 0, icon: "flag", tone: "high" },
  ];
  const total = Math.max(1, (tc.low || 0) + (tc.medium || 0) + (tc.high || 0) + (tc.extreme || 0));

  return (
    <div className="kpis">
      {kpis.map((k) => (
        <div className={"kpi " + k.tone} key={k.label}>
          <span className="kpi-ic"><Icon name={k.icon} size={18} /></span>
          <div><small>{k.label}</small><b>{k.value}{k.unit && <em> {k.unit}</em>}</b></div>
        </div>
      ))}
      <div className="kpi wide">
        <small>Tier mix</small>
        <div className="mix">
          {["low", "medium", "high", "extreme"].map((t) => (
            <span key={t} className={t} style={{ flex: Math.max(tc[t] || 0, 0.0001) }} title={`${t}: ${tc[t] || 0}`} />
          ))}
        </div>
        <div className="mix-legend">
          {["low", "medium", "high", "extreme"].map((t) => (
            <span key={t}><i className={"d " + t} />{t} <b>{tc[t] || 0}</b></span>
          ))}
          <span className="muted">of {total}</span>
        </div>
      </div>
    </div>
  );
}
