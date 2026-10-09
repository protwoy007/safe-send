import { useState, useEffect, useCallback } from "react";
import { api } from "./api.js";
import QueueTable from "./QueueTable.jsx";
import CaseDetail from "./CaseDetail.jsx";
import MetricsStrip from "./MetricsStrip.jsx";
import RecoveryPanel from "./RecoveryPanel.jsx";
import AuditTable from "./AuditTable.jsx";
import Icon from "../ui/icons.jsx";
import "./investigator.css";

const TABS = [
  { id: "pending", label: "Pending", status: "pending_review", icon: "clock" },
  { id: "released", label: "Released", status: "released", icon: "check" },
  { id: "rejected", label: "Rejected", status: "rejected", icon: "x" },
  { id: "audit", label: "Audit log", status: null, icon: "list" },
];

export default function Investigator() {
  const [apiKey, setApiKey] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useState("pending");
  const [recoveryId, setRecoveryId] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const current = TABS.find((t) => t.id === tab);

  const load = useCallback(async () => {
    if (!current.status) return;
    try {
      const data = await api(`/v1/cases?status=${current.status}`, { key: apiKey });
      setCases(data.cases || []);
      setError("");
      setLoaded(true);
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
    setLoaded(false);
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
      <div className="page-inv login-wrap">
        <form onSubmit={submitKey} className="login-card">
          <span className="login-icon"><Icon name="lock" size={28} stroke={2.2} /></span>
          <h1>Investigator access</h1>
          <p>Review held transfers. Only a person releases or rejects a hold.</p>
          <input type="password" placeholder="Paste API key" value={input} onChange={(e) => setInput(e.target.value)} autoFocus />
          {error && <p className="inv-err">{error}</p>}
          <button className="inv-btn primary" type="submit">Enter dashboard</button>
        </form>
      </div>
    );
  }

  const selected = cases.find((c) => c.case_id === selectedId);

  return (
    <div className="page-inv">
      <div className="inv-top">
        <div>
          <h1>Investigator dashboard</h1>
          <p className="inv-sub">Held transfers, evidence and decisions</p>
        </div>
        <div className="inv-live"><i /> Live · refreshes every 5 s
          <button className="inv-btn ghost small" onClick={() => setApiKey("")}>Sign out</button>
        </div>
      </div>

      <MetricsStrip />

      <div className="inv-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={t.id === tab} className={"inv-tab" + (t.id === tab ? " active" : "")} onClick={() => switchTab(t.id)}>
            <Icon name={t.icon} size={16} /> {t.label}
          </button>
        ))}
      </div>

      {error && <p className="inv-err banner">{error}</p>}

      {tab === "audit" ? (
        <AuditTable apiKey={apiKey} />
      ) : (
        <div className="inv-grid">
          <section className="inv-card">
            <h2 className="inv-h">Queue <span className="count">{cases.length}</span></h2>
            <QueueTable cases={cases} loaded={loaded} tab={tab} selectedId={selectedId} onSelect={(id) => { setRecoveryId(null); setSelectedId(id); }} />
          </section>
          <section>
            {recoveryId ? (
              <RecoveryPanel caseId={recoveryId} apiKey={apiKey} onClose={() => setRecoveryId(null)} />
            ) : selected ? (
              <CaseDetail c={selected} apiKey={apiKey} onDone={handleDecided} onShowRecovery={setRecoveryId} />
            ) : (
              <div className="inv-card empty-detail">
                <span className="empty-ic"><Icon name="eye" size={30} /></span>
                <h3>Select a case</h3>
                <p>Choose a case from the queue to see the evidence, the network around the recipient, and to decide.</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
