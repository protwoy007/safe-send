import { useState } from "react";
import { api } from "./api.js";

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
      await api(`/v1/cases/${caseId}/decision`, {
        key: apiKey,
        method: "POST",
        body: { decision, investigator: name.trim(), note },
      });
      setNote("");
      onDone(decision, caseId);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <div className="panel">
      <h3>Decision</h3>
      <input
        placeholder="Investigator name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder="Note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {error && <p className="err">{error}</p>}
      <div className="row">
        <button className="ok" disabled={busy} onClick={() => decide("release")}>Release</button>
        <button className="bad" disabled={busy} onClick={() => decide("reject")}>Reject</button>
      </div>
    </div>
  );
}
