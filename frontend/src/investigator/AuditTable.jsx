import { useEffect, useState } from "react";
import { api } from "./api.js";
import Icon from "../ui/icons.jsx";

const META = {
  transfer_scored: { icon: "shield", cls: "teal", label: "Transfer scored" },
  transfer_completed: { icon: "send", cls: "low", label: "Transfer completed" },
  transfer_cancelled: { icon: "x", cls: "extreme", label: "Transfer cancelled" },
  sender_report: { icon: "flag", cls: "high", label: "Recipient reported" },
  case_opened: { icon: "clock", cls: "extreme", label: "Case opened" },
  case_released: { icon: "check", cls: "low", label: "Case released" },
  case_rejected: { icon: "gavel", cls: "high", label: "Case rejected" },
  ring_flagged: { icon: "network", cls: "high", label: "Ring accounts flagged" },
  // names used by earlier backend versions
  score: { icon: "shield", cls: "teal", label: "Scored" },
  confirm: { icon: "send", cls: "low", label: "Confirmed" },
  report: { icon: "flag", cls: "high", label: "Reported" },
  decision: { icon: "gavel", cls: "medium", label: "Decision" },
  ring_action: { icon: "network", cls: "high", label: "Ring action" },
};

function summary(ev) {
  const d = ev.detail;
  if (d && typeof d === "object") {
    if (ev.type === "score") return `${d.tier || ""} · ${d.action || ""} · ${Number(d.amount || 0).toLocaleString("en-US")} Tk`;
    if (ev.type === "decision") return `${d.decision}${d.note ? " · " + d.note : ""}`;
    return JSON.stringify(d);
  }
  return String(d || "").replace(/=-(\s|$)/g, "=none$1");
}

export default function AuditTable({ apiKey }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const d = await api("/v1/audit?limit=50", { key: apiKey });
        if (alive) { setEvents(d.events || []); setError(""); }
      } catch (e) {
        if (alive) setError(e.message);
      }
    }
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [apiKey]);

  return (
    <div className="inv-card">
      <h2 className="inv-h">Audit trail <span className="count">{events.length}</span></h2>
      <p className="muted small">Append-only record of every score, confirmation, report, decision and ring action.</p>
      {error && <p className="inv-err">{error}</p>}
      {!events.length && !error ? (
        <p className="muted">No audit events yet.</p>
      ) : (
        <ul className="timeline">
          {events.map((ev) => {
            const m = META[ev.type] || { icon: "list", cls: "teal", label: ev.type };
            return (
              <li key={ev.id}>
                <span className={"tl-ic " + m.cls}><Icon name={m.icon} size={16} /></span>
                <div className="tl-body">
                  <div className="tl-top"><b>{m.label}</b><small>#{ev.id} · {String(ev.ts).replace("T", " ").slice(0, 19)}</small></div>
                  <div className="tl-sum">{summary(ev)}</div>
                  <div className="tl-meta">
                    {ev.actor && <span>by {ev.actor}</span>}
                    {ev.tx_ref && <span>{ev.tx_ref}</span>}
                    {ev.case_id && <span>{ev.case_id}</span>}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
