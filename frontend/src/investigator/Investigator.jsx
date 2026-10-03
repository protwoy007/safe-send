import { useState, useEffect, useCallback } from "react";
import { api } from "./api.js";
import QueueTable from "./QueueTable.jsx";
import CaseDetail from "./CaseDetail.jsx";
import MetricsStrip from "./MetricsStrip.jsx";
import "./investigator.css";

export default function Investigator() {
  const [apiKey, setApiKey] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api("/v1/cases?status=pending_review", { key: apiKey });
      setCases(data.cases || []);
      setError("");
    } catch (e) {
      setError(e.message);
      if (e.message === "Invalid key") setApiKey("");
    }
  }, [apiKey]);

  useEffect(() => {
    if (!apiKey) return;
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [apiKey, load]);

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
      <MetricsStrip openCases={cases.length} />
      {error && <p className="err">{error}</p>}
      <div className="grid">
        <div>
          <QueueTable cases={cases} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
        <div>
          {selected ? (
            <CaseDetail
              c={selected}
              apiKey={apiKey}
              onDone={() => {
                setSelectedId(null);
                load();
              }}
            />
          ) : (
            <p>Select a case.</p>
          )}
        </div>
      </div>
    </div>
  );
}

