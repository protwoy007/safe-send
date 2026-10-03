import { useEffect, useState } from "react";
import { api } from "./api.js";

const COLORS = {
  recipient: "#d9534f",
  current_sender: "#f0ad4e",
  sender: "#5bc0de",
  downstream: "#8e44ad",
  peer: "#7f8c8d",
  device: "#2e8b57",
};

const str = (x) =>
  x == null ? "" : typeof x === "object" ? JSON.stringify(x) : String(x);

function Graph({ graph }) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? graph?.links ?? [];
  if (!nodes.length) return <p>No graph data.</p>;

  const W = 520, H = 380, cx = W / 2, cy = H / 2, R = 150;
  const center = nodes.find((n) => n.role === "recipient") ?? nodes[0];
  const others = nodes.filter((n) => n !== center);
  const pos = { [center.id]: [cx, cy] };
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    pos[n.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  });
  const roles = [...new Set(nodes.map((n) => n.role))];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="graph">
        {edges.map((e, i) => {
          const a = pos[e.source ?? e.from];
          const b = pos[e.target ?? e.to];
          if (!a || !b) return null;
          return (
            <line
              key={i}
              x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
              stroke={e.kind === "pending" ? "#d9534f" : "#999"}
              strokeWidth="1.5"
              strokeDasharray={e.kind === "pending" ? "6 4" : undefined}
            />
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.id];
          const label = str(n.label ?? n.id);
          return (
            <g key={n.id}>
              <circle cx={p[0]} cy={p[1]} r="11" fill={COLORS[n.role] ?? "#bbb"}>
                <title>{label + " (" + str(n.role) + ")"}</title>
              </circle>
              <text x={p[0]} y={p[1] + 24} fontSize="9" textAnchor="middle">
                {label.length > 10 ? label.slice(-8) : label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        {roles.map((r) => (
          <span key={r}>
            <i style={{ background: COLORS[r] ?? "#bbb" }} /> {str(r)}
          </span>
        ))}
        <span><i className="dash" /> pending</span>
      </div>
    </div>
  );
}

function Peers({ peers }) {
  if (!peers || !peers.length) return <p>No peers.</p>;
  if (typeof peers[0] !== "object") {
    return <ul>{peers.map((p, i) => <li key={i}>{str(p)}</li>)}</ul>;
  }
  const cols = Object.keys(peers[0]);
  return (
    <div className="scroll">
      <table className="tbl">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {peers.map((p, i) => (
            <tr key={i}>{cols.map((c) => <td key={c}>{str(p[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function NetworkView({ caseId, apiKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    api(`/v1/cases/${caseId}/network?days=7`, { key: apiKey })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [caseId, apiKey]);

  if (error) return <p className="err">{error}</p>;
  if (!data) return <p>Loading network...</p>;

  const notes = data.notes ?? [];
  const m = data.metrics ?? {};
  const cards = Array.isArray(m)
    ? m.map((x) => [x.label ?? x.name, x.value])
    : Object.entries(m);

  return (
    <div className="network">
      <h3>Network (last 7 days)</h3>
      {notes.length > 0 && (
        <ul>{notes.map((n, i) => <li key={i}>{str(n?.text ?? n)}</li>)}</ul>
      )}
      <div className="cards">
        {cards.map(([k, v]) => (
          <div key={k} className="card"><small>{k}</small><b>{str(v)}</b></div>
        ))}
      </div>
      <Graph graph={data.graph ?? data} />
      <h4>Peers</h4>
      <Peers peers={data.peers} />
    </div>
  );
}
