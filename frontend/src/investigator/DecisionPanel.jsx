import { useState } from "react";
import { api } from "./api.js";
import Icon from "../ui/icons.jsx";

export default function DecisionPanel({ caseId, apiKey, onDone }) {
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(decision) {
    if (!name.trim()) {
      setError("Please enter your name.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api(`/v1/cases/${caseId}/decision`, { key: apiKey, method: "POST", body: { decision, investigator: name.trim(), note } });
      setNote("");
      onDone(decision, caseId);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <div className="inv-card decision">
      <h3 className="inv-h"><Icon name="gavel" size={18} /> Your decision</h3>
      <p className="muted small">Nothing is blocked automatically. Release lets the transfer go through; Reject cancels it, flags the recipient and related accounts, and lists the victims to notify.</p>
      <input placeholder="Investigator name" value={name} onChange={(e) => setName(e.target.value)} />
      <textarea placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
      {error && <p className="inv-err">{error}</p>}
      <div className="row">
        <button className="inv-btn ok" disabled={busy} onClick={() => decide("release")}><Icon name="check" size={18} /> Release</button>
        <button className="inv-btn bad" disabled={busy} onClick={() => decide("reject")}><Icon name="x" size={18} /> Reject</button>
      </div>
    </div>
  );
}
