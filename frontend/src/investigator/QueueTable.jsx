import Icon from "../ui/icons.jsx";

const fmtTime = (s) => String(s || "").replace("T", " ").slice(0, 16);

export default function QueueTable({ cases, loaded, tab, selectedId, onSelect }) {
  if (!cases.length) {
    return (
      <div className="queue-empty">
        <span className="empty-ic"><Icon name={loaded ? "check" : "clock"} size={26} /></span>
        <p>{loaded ? (tab === "pending" ? "No pending cases. New holds appear here within seconds." : "Nothing here yet.") : "Loading…"}</p>
      </div>
    );
  }
  return (
    <ul className="queue">
      {cases.map((c) => (
        <li key={c.case_id}>
          <button className={"queue-item" + (c.case_id === selectedId ? " sel" : "")} onClick={() => onSelect(c.case_id)}>
            <div className="qi-top">
              <b>{c.case_id}</b>
              <span className={"tier-badge " + c.tier}><i />{c.tier}</span>
            </div>
            <div className="qi-mid">
              <span className="amt">{Number(c.amount).toLocaleString("en-US")} Tk</span>
              <span className="time">{fmtTime(c.timestamp)}</span>
            </div>
            <div className="qi-risk">
              <div className="rbar"><div className={"rfill " + c.tier} style={{ width: Math.round(c.risk_score * 100) + "%" }} /></div>
              <small>{Number(c.risk_score).toFixed(2)}</small>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
