import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function MetricsStrip({ openCases }) {
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

  function fmt(v) {
    if (v && typeof v === "object") {
      return Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(", ");
    }
    return String(v);
  }

  return (
    <div className="metrics">
      <div><small>open cases</small><b>{openCases}</b></div>
      {m && Object.entries(m).map(([k, v]) => (
        <div key={k}><small>{k}</small><b>{fmt(v)}</b></div>
      ))}
    </div>
  );
}
