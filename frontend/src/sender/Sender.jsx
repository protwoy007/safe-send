import './sender.css';
import { useEffect, useState } from 'react';
import { api, friendly } from './api';
import { T } from './i18n';

const COLORS = { allow: '#1e8e3e', warn: '#e0a800', warn_cooloff: '#c62828', hold_for_review: '#6b7280' };

export default function Sender() {
  const [lang, setLang] = useState('en');
  const t = T[lang];
  const [form, setForm] = useState({ sender_id: '', recipient_id: '', amount: '' });
  const [base, setBase] = useState({});
  const [examples, setExamples] = useState([]);
  const [res, setRes] = useState(null);
  const [final, setFinal] = useState(null);
  const [err, setErr] = useState(null);
  const [left, setLeft] = useState(0);
  const [showReport, setShowReport] = useState(false);

  const fail = (e) => setErr(e);
  const errText = err ? friendly(err, t) : '';

  useEffect(() => {
    api.examples().then(d => setExamples(d.examples)).catch(fail);
  }, []);

  async function loadExample(id) {
    if (!id) return;
    try {
      const b = await api.load(id);
      setBase(b);
      setForm({ sender_id: b.sender_id, recipient_id: b.recipient_id, amount: b.amount });
      reset();
    } catch (e) { fail(e); }
  }

  function reset() {
    setRes(null); setFinal(null); setErr(null); setLeft(0); setShowReport(false);
  }

  async function check(useLang = lang) {
    reset();
    try {
      const r = await api.score({
        tx_type: 'send_money', channel: 'app', device_id: 'DV00123',
        timestamp: new Date().toISOString().slice(0, 19).replace('T', ' '),
        ...base, ...form, amount: Number(form.amount), lang: useLang,
      });
      setRes(r);
      if (r.action === 'warn_cooloff') setLeft(r.cooloff_seconds ?? 30);
      if (r.action === 'allow') {
        await api.confirm(r.tx_ref, 'proceed');
        setFinal('ok');
      }
    } catch (e) { fail(e); }
  }

  // countdown
  useEffect(() => {
    if (left <= 0) return;
    const id = setTimeout(() => setLeft(l => l - 1), 1000);
    return () => clearTimeout(id);
  }, [left]);

  // held: poll every 3 seconds
  useEffect(() => {
    if (res?.action !== 'hold_for_review' || final) return;
    const id = setInterval(async () => {
      try {
        const s = await api.transfer(res.tx_ref);
        if (s.status === 'completed') setFinal('sent');
        if (s.status === 'rejected') setFinal('rejected');
      } catch { /* keep polling */ }
    }, 3000);
    return () => clearInterval(id);
  }, [res, final]);

  async function decide(d) {
    setErr(null);
    try {
      await api.confirm(res.tx_ref, d);
      setFinal(d === 'proceed' ? 'sent' : 'cancelled');
    } catch (e) { fail(e); }
  }

  // Switch language. If a warning is on screen, re-run the check so the
  // server returns the message and reasons in the new language.
  // Not re-run when the transfer is finished or held (it would create a duplicate transfer/case).
  function toggleLang() {
    const next = lang === 'en' ? 'bn' : 'en';
    setLang(next);
    const rerun = res && !final && (res.action === 'warn' || res.action === 'warn_cooloff');
    if (rerun) check(next);
  }

  const color = COLORS[res?.action];
  const canAct = res && !final && (res.action === 'warn' || res.action === 'warn_cooloff');

  return (
    <main className="app">
      <header className="top">
        <h1>{t.title}</h1>
        <button className="lang" onClick={toggleLang}>
          {lang === 'en' ? 'বাংলা' : 'English'}
        </button>
      </header>

      <select className="field" defaultValue="" onChange={e => loadExample(e.target.value)}>
        <option value="">{t.demo}</option>
        {examples.map(x => <option key={x.example_id} value={x.example_id}>{x.title}</option>)}
      </select>

      <label>{t.sender}
        <input className="field" value={form.sender_id} onChange={e => setForm({ ...form, sender_id: e.target.value })} />
      </label>
      <label>{t.recipient}
        <input className="field" value={form.recipient_id} onChange={e => setForm({ ...form, recipient_id: e.target.value })} />
      </label>
      <label>{t.amount}
        <input className="field" type="number" inputMode="numeric" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
      </label>

      <button className="btn primary" onClick={() => check()}>{t.check}</button>

      {errText && <p className="error" role="alert">{errText}</p>}

      {res && !final && (
        <section className="card" style={{ borderColor: color }}>
          {res.action === 'hold_for_review' ? (
            <>
              <p className="msg">{t.held}</p>
              <p className="muted">{t.waiting}</p>
            </>
          ) : (
            <p className="msg">{res.message}</p>
          )}

          {res.reasons?.map(r => <div key={r.code} className="reason">{r.text}</div>)}

          {canAct && (
            <>
              <button className="btn" disabled={left > 0} onClick={() => decide('proceed')}>
                {left > 0 ? `${t.sendAnyway} (${left})` : t.sendAnyway}
              </button>
              <button className="btn secondary" onClick={() => decide('cancel')}>{t.cancel}</button>
            </>
          )}

          {res.action === 'warn_cooloff' && res.can_report && (
            <>
              <button className="btn secondary" onClick={() => setShowReport(true)}>{t.report}</button>
              {showReport && <ReportForm t={t} form={form} txRef={res.tx_ref} />}
            </>
          )}
        </section>
      )}

      {final && (
        <section className="card" style={{ borderColor: final === 'sent' || final === 'ok' ? COLORS.allow : COLORS.hold_for_review }}>
          <p className="msg">{t[final]}</p>
          <button className="btn secondary" onClick={() => { reset(); setForm({ sender_id: '', recipient_id: '', amount: '' }); setBase({}); }}>
            {t.again}
          </button>
        </section>
      )}
    </main>
  );
}

function ReportForm({ t, form, txRef }) {
  const [note, setNote] = useState('');
  const [done, setDone] = useState(false);
  const [err, setErr] = useState(null);

  if (done) return <p className="thanks">{t.thanks}</p>;

  const submit = () =>
    api.report({ sender_id: form.sender_id, recipient_id: form.recipient_id, tx_ref: txRef, note })
      .then(() => setDone(true))
      .catch(setErr);

  return (
    <div>
      <textarea className="field" rows={3} maxLength={300} placeholder={t.note}
        value={note} onChange={e => setNote(e.target.value)} />
      <button className="btn" onClick={submit}>{t.submit}</button>
      {err && <p className="error">{friendly(err, t)}</p>}
    </div>
  );
}