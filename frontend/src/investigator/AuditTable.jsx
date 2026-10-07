import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function AuditTable({ apiKey }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const d = await api("/v1/audit?limit=50", { key: apiKey });
        if (alive) {
          setEvents(d.events || []);
          setError("");
        }
      } catch (e) {
        if (alive) setError(e.message);
      }
    }
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [apiKey]);

  return (
    <div>
      {error && <p className="err">{error}</p>}
      {!events.length && !error ? (
        <p>No audit events.</p>
      ) : (
        <table className="tbl nohover">
          <thead>
            <tr>
              <th>ID</th><th>Time</th><th>Type</th><th>Actor</th><th>Tx</th><th>Case</th><th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => (
              <tr key={ev.id}>
                <td>{ev.id}</td>
                <td>{ev.ts}</td>
                <td>{ev.type}</td>
                <td>{ev.actor}</td>
                <td>{ev.tx_ref}</td>
                <td>{ev.case_id}</td>
                <td>{typeof ev.detail === "object" ? JSON.stringify(ev.detail) : ev.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
