import { useEffect, useState } from "react";
import { api } from "./api.js";

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
    return () => {
      alive = false;
    };
  }, [caseId, apiKey]);

  function copyList() {
    const lines = (data.earlier_senders || []).map(
      (s) => `${s.sender_id}\t${s.amount_tk} Tk\t${s.time}`
    );
    const text = lines.join("\n");
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };
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
    try {
      document.execCommand("copy");
      done();
    } catch {
      /* ignore */
    }
    document.body.removeChild(ta);
  }

  return (
    <div className="detail">
      <div className="row spread">
        <h2>Victims to notify</h2>
        <button className="gray" onClick={onClose}>Close</button>
      </div>
      {error && <p className="err">{error}</p>}
      {!data && !error && <p>Loading…</p>}
      {data && (
        <>
          <p><b>Case:</b> {data.case_id} &nbsp; <b>Recipient:</b> {data.recipient_id}</p>
          {data.earlier_senders && data.earlier_senders.length ? (
            <table className="tbl nohover">
              <thead>
                <tr><th>Sender</th><th>Amount</th><th>Time</th></tr>
              </thead>
              <tbody>
                {data.earlier_senders.map((s, i) => (
                  <tr key={i}>
                    <td>{s.sender_id}</td>
                    <td>{s.amount_tk} Tk</td>
                    <td>{s.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No earlier senders.</p>
          )}
          <p><b>Earlier total:</b> {data.earlier_total_tk} Tk</p>
          <p><b>This transfer:</b> {data.this_transfer_tk} Tk</p>
          <p><b>Peers flagged:</b> {(data.peers_flagged || []).join(", ") || "None"}</p>
          <p><b>People to notify:</b> {data.notify_count}</p>
          <button className="ok" onClick={copyList}>{copied ? "Copied" : "Copy list"}</button>
        </>
      )}
    </div>
  );
}
