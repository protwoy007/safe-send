import { useEffect, useState } from "react";
import { api } from "./api.js";

const COLORS = {
  recipient: "#c0392b",
  current_sender: "#2980b9",
  sender: "#5dade2",
  downstream: "#e67e22",
  peer: "#8e44ad",
  device: "#7f8c8d",
};
const W = 600;
const H = 420;

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
    return () => {
      alive = false;
    };
  }, [caseId, apiKey]);

  if (error) return <p className="err">{error}</p>;
  if (!data) return <p>Loading network…</p>;

  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const notes = data.notes || [];
  const peers = data.peers || [];
  const metrics = data.metrics || {};

  const center =
    nodes.find((n) => n.role === "recipient") ||
    nodes.find((n) => n.id === recipientId) ||
    nodes[0];
  const others = nodes.filter((n) => n !== center);
  const cx = W / 2;
  const cy = H / 2;
  const radius = 160;
  const pos = {};
  if (center) pos[center.id] = { x: cx, y: cy };
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    pos[n.id] = { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) };
  });

  return (
    <div className="network">
      <h3>Network</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#666" />
          </marker>
        </defs>
        {edges.map((e, i) => {
          const s = pos[e.source];
          const t = pos[e.target];
          if (!s || !t) return null;
          return (
            <g key={i}>
              <line
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke="#666"
                strokeWidth="1.5"
                strokeDasharray={e.kind === "pending" ? "6 4" : undefined}
                markerEnd="url(#arrow)"
              />
              <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2 - 4} fontSize="10" textAnchor="middle" fill="#333">
                {e.amount} Tk{e.count > 1 ? ` ×${e.count}` : ""}
              </text>
            </g>
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          return (
            <g key={n.id}>
              <circle cx={p.x} cy={p.y} r={n === center ? 24 : 18} fill={COLORS[n.role] || "#999"} stroke="#fff" strokeWidth="2" />
              <text x={p.x} y={p.y + (n === center ? 38 : 32)} fontSize="11" textAnchor="middle" fill="#222">
                {short(n.id)}
              </text>
              <title>
                {n.id} | {n.role} | age {n.age_days}d | in {n.in_degree} / out {n.out_degree}
              </title>
            </g>
          );
        })}
      </svg>

      <div className="legend">
        {Object.entries(COLORS).map(([role, color]) => (
          <span key={role}>
            <i style={{ background: color }} /> {role}
          </span>
        ))}
        <span>
          <i className="dash" /> pending
        </span>
      </div>

      {Object.keys(metrics).length > 0 && (
        <div className="metrics">
          {Object.entries(metrics).map(([k, v]) => (
            <div key={k}>
              <small>{k}</small>
              <b>{typeof v === "object" ? JSON.stringify(v) : String(v)}</b>
            </div>
          ))}
        </div>
      )}

      <h3>Notes</h3>
      {notes.length ? (
        <ul>
          {notes.map((n, i) => (
            <li key={i}>{typeof n === "string" ? n : JSON.stringify(n)}</li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}

      {peers.length > 0 && (
        <>
          <h3>Peers</h3>
          <ul>
            {peers.map((p, i) => (
              <li key={i}>
                <b>{p.id}</b>: {p.reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
