import { useEffect, useRef, useState } from "react";
import { getImpact, impactError } from "./api";
import Icon from "../ui/icons.jsx";
import "./impact.css";

const LABELS = {
  monthly_transfers: "Transfers per month",
  scam_rate: "Scam rate",
  avg_loss_tk: "Average loss per scam (Tk)",
  recall: "Model recall (scams caught)",
  warn_effect: "Warning effect (scams stopped)",
  false_positive_rate: "False-positive rate",
  legit_abandon: "Honest users who give up after a warning",
  avg_legit_value_tk: "Average honest transfer (Tk)",
  fee_rate: "Fee rate",
  cases_per_10k: "Review cases per 10,000 transfers",
  cost_per_case_tk: "Cost per review case (Tk)",
  pilot_relative_reduction: "Pilot: reduction to detect",
};
const RATES = ["scam_rate", "recall", "warn_effect", "false_positive_rate",
  "legit_abandon", "fee_rate", "pilot_relative_reduction"];

const tk = (n) => `${Math.round(Number(n) || 0).toLocaleString("en-US")} Tk`;
const pct = (n) => `${(Number(n) * 100).toFixed(1)}%`;

// Slider range is built from the server default, so nothing is hard-coded.
function range(key, def) {
  const d = Number(def) || 0;
  let max = d > 0 ? d * 3 : 1;
  if (RATES.includes(key)) max = Math.min(1, Math.max(max, d * 3));
  const raw = max / 200;
  const pow = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const step = Math.max(pow * Math.round(raw / pow || 1), 1e-6);
  return { min: 0, max, step };
}

export default function Impact() {
  const [defaults, setDefaults] = useState(null);
  const [vals, setVals] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);

  // 1) First call: no params. Prefill sliders from `inputs`.
  useEffect(() => {
    getImpact()
      .then((d) => { setDefaults(d.inputs); setVals(d.inputs); setData(d); setErr(""); })
      .catch((e) => setErr(impactError(e)))
      .finally(() => setLoading(false));
  }, []);

  // 2) After any change: call again (wait 300 ms so we do not spam the server).
  useEffect(() => {
    if (!vals || vals === defaults) return;
    const id = ++seq.current;
    const timer = setTimeout(() => {
      getImpact(vals)
        .then((d) => { if (id === seq.current) { setData(d); setErr(""); } })
        .catch((e) => { if (id === seq.current) setErr(impactError(e)); });
    }, 300);
    return () => clearTimeout(timer);
  }, [vals]);

  const set = (k, v) => setVals({ ...vals, [k]: v });
  const r = data?.results;
  const sens = data?.sensitivity ?? [];
  const maxAbs = Math.max(1, ...sens.map((s) => Math.abs(s.net_benefit_tk)));

  const good = r && r.net_benefit_tk >= 0;
  return (
    <main className="imp-wrap">
      <header className="imp-hero">
        <span className="imp-eyebrow"><Icon name="chart" size={16} /> Impact estimate</span>
        <h1>What could Safe-Send be worth?</h1>
        <p className="imp-sub">A transparent, assumption-based estimate. Move the sliders to test every assumption.</p>
      </header>

      {loading && <p className="imp-muted"><span className="spinner" /> Loading…</p>}
      {err && <p className="imp-error" role="alert">{err}</p>}

      {data && (
        <div className="imp-layout">
          <div className="imp-main">
            <section className={"imp-net " + (good ? "good" : "bad")}>
              <small>Net benefit per month</small>
              <b>{tk(r.net_benefit_tk)}</b>
              <span>{Math.round(r.legit_warned)} honest transfers warned · break-even warning effect {pct(r.break_even_warn_effect)}</span>
            </section>

            <section className="imp-cards">
              <Card icon="shield" title="Scam losses prevented" value={tk(r.prevented_value_tk)} tone="good"
                note={`${Math.round(r.scams_warned)} of ${Math.round(r.scams_per_month)} scams warned per month`} />
              <Card icon="coin" title="Costs" value={tk(r.revenue_lost_tk + r.investigator_cost_tk)} tone="bad"
                note={`Lost fees ${tk(r.revenue_lost_tk)} · Investigators ${tk(r.investigator_cost_tk)}`} />
            </section>

            <section className="imp-box">
              <h2>Net benefit if the warning effect changes</h2>
              {sens.map((s) => {
                const w = (Math.abs(s.net_benefit_tk) / maxAbs) * 100;
                const neg = s.net_benefit_tk < 0;
                return (
                  <div className="imp-row" key={s.warn_effect}>
                    <span className="imp-lab">{pct(s.warn_effect)}</span>
                    <div className="imp-track">
                      <div className={`imp-bar ${neg ? "neg" : "pos"}`} style={{ width: `${w}%` }} />
                    </div>
                    <span className={`imp-val ${neg ? "neg" : ""}`}>{tk(s.net_benefit_tk)}</span>
                  </div>
                );
              })}
            </section>

            <section className="imp-box imp-pilot">
              <span className="imp-pilot-ic"><Icon name="users" size={22} /></span>
              <div>
                <h2>Pilot sample size</h2>
                <p className="imp-big">{Number(data.pilot.n_per_arm).toLocaleString("en-US")} <small>users per group</small></p>
                <p className="imp-muted">{data.pilot.assumption}</p>
              </div>
            </section>

            <section className="imp-disclaimer" role="note">
              <Icon name="alert" size={20} /> <div><b>Important:</b> {data.disclaimer}</div>
            </section>
          </div>

          {vals && (
            <aside className="imp-box imp-assume">
              <h2>Assumptions</h2>
              {Object.keys(LABELS).filter((k) => k in vals).map((k) => {
                const { min, max, step } = range(k, defaults[k]);
                const shown = RATES.includes(k) ? `${(vals[k] * 100).toFixed(1)}%` : Number(vals[k]).toLocaleString("en-US");
                return (
                  <div className="imp-input" key={k}>
                    <label htmlFor={k}>{LABELS[k]} <b>{shown}</b></label>
                    <input id={k} type="range" min={min} max={max} step={step}
                      value={vals[k]} onChange={(e) => set(k, Number(e.target.value))} />
                  </div>
                );
              })}
              <button className="imp-reset" onClick={() => { setVals(defaults); getImpact().then(setData).catch((e) => setErr(impactError(e))); }}>
                Reset to defaults
              </button>
            </aside>
          )}
        </div>
      )}
    </main>
  );
}

function Card({ title, value, note, tone, icon }) {
  return (
    <div className={`imp-card ${tone}`}>
      <span className="imp-card-ic"><Icon name={icon || "chart"} size={20} /></span>
      <div>
        <div className="imp-card-title">{title}</div>
        <div className="imp-card-value">{value}</div>
        <div className="imp-card-note">{note}</div>
      </div>
    </div>
  );
}
