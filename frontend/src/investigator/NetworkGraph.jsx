import { useEffect, useState } from "react";
import { api } from "./api.js";

const COLORS = {
  recipient: "#dc2626", current_sender: "#0f5c5c", sender: "#5aa7a3",
  downstream: "#f2a541", peer: "#7c3aed", device: "#64748b",
};
const LABEL = { recipient: "Recipient", current_sender: "This sender", sender: "Earlier sender", downstream: "Paid out to", peer: "Related account", device: "Shared device" };
const W = 640;
const H = 440;
const METRIC = {
  recipient_age_days: "Recipient age (days)", distinct_senders_incl_this: "Distinct senders", inflow_tk: "Inflow (Tk)",
  outflow_tk: "Outflow (Tk)", paid_out_ratio: "Paid-out ratio", paid_to_agents: "Paid to agents", peer_accounts: "Related accounts",
  shared_devices: "Shared devices", component_size: "Cluster size", pagerank_recipient: "PageRank", window_days: "Window (days)",
};

function short(id) {
  const s = String(id);
  return s.length > 12 ? s.slice(0, 11) + "…" : s;
}

export default function NetworkGraph({ caseId, recipientId, apiKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    api(`/v1/cases/${caseId}/network`, { key: apiKey })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [caseId, apiKey]);

  if (error) return <div className="inv-card"><p className="inv-err">{error}</p></div>;
  if (!data) return <div className="inv-card"><p className="muted"><span className="spinner" /> Loading network…</p></div>;

  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const notes = data.notes || [];
  const peers = data.peers || [];
  const metrics = data.metrics || {};

  const center = nodes.find((n) => n.role === "recipient") || nodes.find((n) => n.id === recipientId) || nodes[0];
  const others = nodes.filter((n) => n !== center);
  const cx = W / 2, cy = H / 2, radius = 165;
  const pos = {};
  if (center) pos[center.id] = { x: cx, y: cy };
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    pos[n.id] = { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) * 0.86 };
  });
  const used = Object.keys(COLORS).filter((r) => nodes.some((n) => n.role === r));

  return (
    <div className="inv-card network">
      <h3 className="inv-h">Network around the recipient</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="graph" role="img" aria-label="Transaction network">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8aa09e" />
          </marker>
          <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#0f2a2b" floodOpacity=".25" />
          </filter>
        </defs>
        <circle cx={cx} cy={cy} r={radius + 36} fill="none" stroke="#e3ecea" strokeDasharray="3 6" />
        {edges.map((e, i) => {
          const s = pos[e.source];
          const t = pos[e.target];
          if (!s || !t) return null;
          const dx = t.x - s.x, dy = t.y - s.y, len = Math.hypot(dx, dy) || 1;
          const tr = (t.x === cx && t.y === cy ? 30 : 22) / len;
          const ex = t.x - dx * tr, ey = t.y - dy * tr;
          const pending = e.kind === "pending";
          const label = e.kind === "uses_device" || e.kind === "similar_pattern" ? null : `${Number(e.amount).toLocaleString("en-US")}${e.count > 1 ? ` ×${e.count}` : ""}`;
          const mx = (s.x + ex) / 2, my = (s.y + ey) / 2;
          return (
            <g key={i}>
              <line x1={s.x} y1={s.y} x2={ex} y2={ey} stroke={pending ? "#dc2626" : "#8aa09e"} strokeWidth={pending ? 2.5 : 1.6}
                strokeDasharray={pending || e.kind === "similar_pattern" || e.kind === "uses_device" ? "6 5" : undefined} markerEnd="url(#arrow)" opacity={pending ? 1 : 0.8} />
              {label && (
                <g>
                  <rect x={mx - 22} y={my - 17} width="44" height="15" rx="7" fill="#fff" stroke="#dbe6e4" />
                  <text x={mx} y={my - 6} fontSize="9.5" textAnchor="middle" fill="#3d5857" fontWeight="600">{label}</text>
                </g>
              )}
            </g>
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const big = n === center;
          return (
            <g key={n.id} filter="url(#shadow)">
              {big && <circle cx={p.x} cy={p.y} r="38" fill={COLORS.recipient} opacity=".12" />}
              <circle cx={p.x} cy={p.y} r={big ? 26 : 19} fill={COLORS[n.role] || "#999"} stroke="#fff" strokeWidth="3" />
              <rect x={p.x - 38} y={p.y + (big ? 32 : 25)} width="76" height="16" rx="8" fill="#fff" opacity=".92" />
              <text x={p.x} y={p.y + (big ? 43.5 : 36.5)} fontSize="10.5" textAnchor="middle" fill="#0f2a2b" fontWeight="600">{short(n.id)}</text>
              <title>{n.id} | {LABEL[n.role] || n.role} | age {n.age_days}d | in {n.in_degree} / out {n.out_degree}</title>
            </g>
          );
        })}
      </svg>

      <div className="legend">
        {used.map((role) => <span key={role}><i style={{ background: COLORS[role] }} />{LABEL[role]}</span>)}
        <span><i className="dash" /> this transfer</span>
      </div>

      {Object.keys(metrics).length > 0 && (
        <div className="net-metrics">
          {Object.entries(metrics).map(([k, v]) => (
            <div key={k}><small>{METRIC[k] || k}</small><b>{v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v)}</b></div>
          ))}
        </div>
      )}

      <h3 className="inv-h sub">Findings</h3>
      {notes.length ? (
        <ul className="notes">{notes.map((n, i) => <li key={i}>{typeof n === "string" ? n : JSON.stringify(n)}</li>)}</ul>
      ) : <p className="muted">None</p>}

      {peers.length > 0 && (
        <>
          <h3 className="inv-h sub">Related accounts (leads, not proof)</h3>
          <div className="chips">
            {peers.map((p, i) => <span className="rule" key={i}>{p.id} · {String(p.reason).replace("_", " ")}</span>)}
          </div>
        </>
      )}
    </div>
  );
}
