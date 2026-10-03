export default function QueueTable({ cases, selectedId, onSelect }) {
  if (!cases.length) return <p>No pending cases.</p>;
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Case</th><th>Time</th><th>Amount</th><th>Risk</th><th>Tier</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr
            key={c.case_id}
            className={c.case_id === selectedId ? "sel" : ""}
            onClick={() => onSelect(c.case_id)}
          >
            <td>{c.case_id}</td>
            <td>{c.timestamp}</td>
            <td>{c.amount} Tk</td>
            <td>{Number(c.risk_score).toFixed(2)}</td>
            <td><span className={"tier " + c.tier}>{c.tier}</span></td>
            <td>{c.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
