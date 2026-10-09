import { useEffect, useState } from "react";
import { api } from "./api.js";
import Icon from "../ui/icons.jsx";

export default function RecoveryPanel({ caseId, apiKey, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    setCopied(false);
    api(`/v1/cases/${caseId}/recovery`, { key: apiKey })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [caseId, apiKey]);

  function copyList() {
    const lines = (data.earlier_senders || []).map((s) => `${s.sender_id}\t${s.amount_tk} Tk\t${s.time}`);
    const text = lines.join("\n");
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 2000); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallback(text, done));
    } else {
      fallback(text, done);
    }
  }

  function fallback(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch { /* ignore */ }
    document.body.removeChild(ta);
  }

  return (
    <div className="case">
      <div className="inv-card">
        <div className="row spread">
          <div>
            <p className="eyebrow">Ring action</p>
            <h2 className="inv-h big">Victims to notify</h2>
          </div>
          <button className="inv-btn ghost small" onClick={onClose}>Close</button>
        </div>
        {error && <p className="inv-err">{error}</p>}
        {!data && !error && <p className="muted"><span className="spinner" /> Loading…</p>}
        {data && (
          <>
            <p className="muted">Case {data.case_id} · recipient <b>{data.recipient_id}</b> was confirmed as fraud.</p>
            <div className="stats">
              <div><small>People to notify</small><b>{data.notify_count}</b></div>
              <div><small>Earlier total</small><b>{Number(data.earlier_total_tk).toLocaleString("en-US")} Tk</b></div>
              <div className="good"><small>Stopped now</small><b>{Number(data.this_transfer_tk).toLocaleString("en-US")} Tk</b></div>
              <div><small>Related accounts flagged</small><b>{(data.peers_flagged || []).length}</b></div>
            </div>
            {(data.peers_flagged || []).length > 0 && (
              <div className="chips">{data.peers_flagged.map((p) => <span className="rule" key={p}>{p}</span>)}</div>
            )}
            {data.earlier_senders && data.earlier_senders.length ? (
              <table className="inv-tbl">
                <thead><tr><th>Sender</th><th>Amount</th><th>Time</th></tr></thead>
                <tbody>
                  {data.earlier_senders.map((s, i) => (
                    <tr key={i}><td>{s.sender_id}</td><td>{Number(s.amount_tk).toLocaleString("en-US")} Tk</td><td>{String(s.time).replace("T", " ").slice(0, 16)}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted">No earlier senders in the window.</p>}
            <button className="inv-btn ok block" onClick={copyList}><Icon name="copy" size={18} /> {copied ? "Copied" : "Copy list"}</button>
          </>
        )}
      </div>
    </div>
  );
}
