import DecisionPanel from "./DecisionPanel.jsx";
import NetworkGraph from "./NetworkGraph.jsx";
import Gauge from "../ui/Gauge.jsx";
import Icon from "../ui/icons.jsx";

const RICON = { FAN_IN: "users", NEW_ACCOUNT: "user", RETURN: "repeat", AMOUNT: "trend", DEVICE: "device", NEW_RECIPIENT: "user", TIME: "moon", VELOCITY: "clock", CASHOUT: "coin" };
const RULE_TEXT = {
  R1_LARGE_AMOUNT: "Very large amount",
  R2_REPEATED_USER_REPORTS: "Reported by several users",
  R3_INVESTIGATOR_CONFIRMED_FRAUD: "Recipient confirmed as fraud earlier",
  R4_RING_PEER_WATCHLIST: "Linked to a confirmed-fraud ring",
};

export default function CaseDetail({ c, apiKey, onDone, onShowRecovery }) {
  const reasons = c.reasons || [];
  const max = Math.max(...reasons.map((r) => r.impact), 0.0001);
  const pending = c.status === "pending_review";
  return (
    <div className="case">
      <div className="inv-card case-head">
        <div className="ch-left">
          <p className="eyebrow">Case</p>
          <h2>{c.case_id}</h2>
          <span className={"tier-badge " + c.status}>{c.status.replace("_", " ")}</span>
        </div>
        <Gauge score={c.risk_score} tier={c.tier} size={190} />
      </div>

      <div className="facts">
        <div><small>Sender</small><b>{c.sender_id}</b></div>
        <div><small>Recipient</small><b>{c.recipient_id}</b></div>
        <div><small>Amount</small><b>{Number(c.amount).toLocaleString("en-US")} Tk</b></div>
        <div><small>Tier</small><b className={"t " + c.tier}>{c.tier}</b></div>
      </div>

      <div className="inv-card">
        <h3 className="inv-h">Why it was flagged</h3>
        {reasons.length ? reasons.map((r) => (
          <div key={r.code} className="reason-row">
            <span className="ri"><Icon name={RICON[r.code] || "alert"} size={18} /></span>
            <div className="rr-body">
              <div>{r.text}</div>
              <div className="rr-bar"><div style={{ width: (r.impact / max) * 100 + "%" }} /></div>
              <small>impact {r.impact}</small>
            </div>
          </div>
        )) : <p className="muted">No reasons recorded.</p>}

        <h3 className="inv-h sub">Rules triggered</h3>
        {c.triggered_rules && c.triggered_rules.length ? (
          <div className="chips">
            {c.triggered_rules.map((t, i) => (
              <span className="rule" key={i} title={typeof t === "string" ? t : ""}>{RULE_TEXT[t] || (typeof t === "string" ? t : JSON.stringify(t))}</span>
            ))}
          </div>
        ) : <p className="muted">None</p>}
      </div>

      <NetworkGraph caseId={c.case_id} recipientId={c.recipient_id} apiKey={apiKey} />

      {c.status === "rejected" && (
        <button className="inv-btn bad block" onClick={() => onShowRecovery(c.case_id)}><Icon name="users" size={18} /> Victims to notify</button>
      )}
      {pending && <DecisionPanel caseId={c.case_id} apiKey={apiKey} onDone={onDone} />}
    </div>
  );
}
