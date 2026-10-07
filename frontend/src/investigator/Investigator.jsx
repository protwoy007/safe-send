import { useState, useEffect, useCallback } from "react";
import { api } from "./api.js";
import QueueTable from "./QueueTable.jsx";
import CaseDetail from "./CaseDetail.jsx";
import MetricsStrip from "./MetricsStrip.jsx";
import RecoveryPanel from "./RecoveryPanel.jsx";
import AuditTable from "./AuditTable.jsx";
import "./investigator.css";

const TABS = [
  { id: "pending", label: "Pending", status: "pending_review" },
  { id: "released", label: "Released", status: "released" },
  { id: "rejected", label: "Rejected", status: "rejected" },
  { id: "audit", label: "Audit", status: null },
];

export default function Investigator() {
  const [apiKey, setApiKey] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useState("pending");
  const [recoveryId, setRecoveryId] = useState(null);

  const current = TABS.find((t) => t.id === tab);

  const load = useCallback(async () => {
    if (!current.status) return;
    try {
      const data = await api(`/v1/cases?status=${current.status}`, { key: apiKey });
      setCases(data.cases || []);
      setError("");
    } catch (e) {
      setError(e.message);
      if (e.message === "Invalid key") setApiKey("");
    }
  }, [apiKey, current]);

  useEffect(() => {
    if (!apiKey || !current.status) return;
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [apiKey, current, load]);

  function switchTab(id) {
    setTab(id);
    setCases([]);
    setSelectedId(null);
    setRecoveryId(null);
    setError("");
  }

  async function submitKey(e) {
    e.preventDefault();
    try {
      await api("/v1/cases?status=pending_review", { key: input });
      setApiKey(input);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  function handleDecided(decision, caseId) {
    setSelectedId(null);
    if (decision === "reject") setRecoveryId(caseId);
    load();
  }

  if (!apiKey) {
    return (
      <div className="wrap">
        <h1>Investigator login</h1>
        <form onSubmit={submitKey} className="panel">
          <input
            type="password"
            placeholder="Paste API key"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          {error && <p className="err">{error}</p>}
          <button className="ok" type="submit">Enter</button>
        </form>
      </div>
    );
  }

  const selected = cases.find((c) => c.case_id === selectedId);

  return (
    <div className="wrap">
      <h1>Investigator dashboard</h1>
      <MetricsStrip />
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={"tab" + (t.id === tab ? " active" : "")}
            onClick={() => switchTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {error && <p className="err">{error}</p>}
      {tab === "audit" ? (
        <AuditTable apiKey={apiKey} />
      ) : (
        <div className="grid">
          <div>
            <QueueTable cases={cases} selectedId={selectedId} onSelect={(id) => { setRecoveryId(null); setSelectedId(id); }} />
          </div>
          <div>
            {recoveryId ? (
              <RecoveryPanel caseId={recoveryId} apiKey={apiKey} onClose={() => setRecoveryId(null)} />
            ) : selected ? (
              <CaseDetail
                c={selected}
                apiKey={apiKey}
                onDone={handleDecided}
                onShowRecovery={setRecoveryId}
              />
            ) : (
              <p>Select a case.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
