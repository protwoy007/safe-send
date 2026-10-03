import DecisionPanel from "./DecisionPanel.jsx";
import NetworkView from "./NetworkView.jsx";

export default function CaseDetail({ c, apiKey, onDone, canDecide }) {
  const reasons = c.reasons || [];
  const max = Math.max(...reasons.map((r) => r.impact), 0.0001);
  const rules = c.triggered_rules || [];
  return (
    <div className="detail">
      <h2>Case {c.case_id}</h2>
      <p><b>Status:</b> <span className="tier">{c.status}</span></p>
      <p><b>Sender:</b> {c.sender_id}</p>
      <p><b>Recipient:</b> {c.recipient_id}</p>
      <p><b>Amount:</b> {c.amount} Tk</p>
      <p><b>Risk score:</b> {Number(c.risk_score).toFixed(2)} ({c.tier})</p>
      {c.decision && (
        <p>
          <b>Decision:</b> {c.decision} by {c.investigator}
          {c.note ? " - " + c.note : ""}
        </p>
      )}
      <h3>Reasons</h3>
      {reasons.map((r) => (
        <div key={r.code} className="reason">
          <div>{r.text}</div>
          <div className="barbg">
            <div className="bar" style={{ width: (r.impact / max) * 100 + "%" }} />
          </div>
          <small>impact {r.impact}</small>
        </div>
      ))}
      <h3>Triggered rules</h3>
      {rules.length ? (
        <ul>
          {rules.map((t, i) => (
            <li key={i}>{typeof t === "string" ? t : JSON.stringify(t)}</li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}
      {canDecide && (
        <DecisionPanel caseId={c.case_id} apiKey={apiKey} onDone={onDone} />
      )}
      <NetworkView caseId={c.case_id} apiKey={apiKey} />
    </div>
  );
}
