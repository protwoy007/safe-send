import './sender.css';
import { useEffect, useState } from 'react';
import { api, friendly } from './api';
import { T } from './i18n';
import Icon from '../ui/icons.jsx';
import Ring from '../ui/Ring.jsx';

const KIND = { allow: 'low', warn: 'medium', warn_cooloff: 'high', hold_for_review: 'extreme' };
const ICON = { low: 'check', medium: 'alert', high: 'alert', extreme: 'clock' };
const REASON_ICON = {
  FAN_IN: 'users', NEW_ACCOUNT: 'user', RETURN: 'repeat', AMOUNT: 'trend', DEVICE: 'device',
  NEW_RECIPIENT: 'user', TIME: 'moon', VELOCITY: 'clock', CASHOUT: 'coin',
};
const TITLE_KEY = { low: 'tLow', medium: 'tMed', high: 'tHigh', extreme: 'tExt' };

export default function Sender() {
  const [lang, setLang] = useState('en');
  const t = T[lang];
  const [form, setForm] = useState({ sender_id: '', recipient_id: '', amount: '' });
  const [base, setBase] = useState({});
  const [examples, setExamples] = useState([]);
  const [picked, setPicked] = useState('');
  const [res, setRes] = useState(null);
  const [final, setFinal] = useState(null);
  const [err, setErr] = useState(null);
  const [left, setLeft] = useState(0);
  const [total, setTotal] = useState(30);
  const [showReport, setShowReport] = useState(false);
  const [busy, setBusy] = useState(false);

  const fail = (e) => setErr(e);
  const errText = err ? friendly(err, t) : '';

  useEffect(() => {
    api.examples().then(d => setExamples(d.examples)).catch(fail);
  }, []);

  async function loadExample(id) {
    if (!id) return;
    try {
      const b = await api.load(id);
      setBase(b); setPicked(id);
      setForm({ sender_id: b.sender_id, recipient_id: b.recipient_id, amount: b.amount });
      reset();
    } catch (e) { fail(e); }
  }

  function reset() {
    setRes(null); setFinal(null); setErr(null); setLeft(0); setShowReport(false);
  }

  async function check(useLang = lang) {
    reset(); setBusy(true);
    try {
      const r = await api.score({
        tx_type: 'send_money', channel: 'app', device_id: 'DV00123',
        timestamp: new Date().toISOString().slice(0, 19).replace('T', ' '),
        ...base, ...form, amount: Number(form.amount), lang: useLang,
      });
      setRes(r);
      if (r.action === 'warn_cooloff') { setTotal(r.cooloff_seconds ?? 30); setLeft(r.cooloff_seconds ?? 30); }
      if (r.action === 'allow') {
        await api.confirm(r.tx_ref, 'proceed');
        setFinal('ok');
      }
    } catch (e) { fail(e); }
    setBusy(false);
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
  function toggleLang() {
    const next = lang === 'en' ? 'bn' : 'en';
    setLang(next);
    const rerun = res && !final && (res.action === 'warn' || res.action === 'warn_cooloff');
    if (rerun) check(next);
  }

  const kind = res ? KIND[res.action] : null;
  const canAct = res && !final && (res.action === 'warn' || res.action === 'warn_cooloff');
  const score = res ? Math.round(res.risk_score * 100) : 0;

  return (
    <div className="page-sender">
      <aside className="ss-hero">
        <span className="ss-eyebrow"><Icon name="shield" size={16} /> Safe-Send</span>
        <h1>{t.heroTitle}</h1>
        <p className="ss-sub">{t.heroSub}</p>
        <h3>{t.legend}</h3>
        <ul className="ss-legend">
          <li><i className="d low" />{t.lgLow}</li>
          <li><i className="d medium" />{t.lgMed}</li>
          <li><i className="d high" />{t.lgHigh}</li>
          <li><i className="d extreme" />{t.lgExt}</li>
        </ul>
        <ul className="ss-trust">
          <li><Icon name="lock" size={18} />{t.trust1}</li>
          <li><Icon name="clock" size={18} />{t.trust2}</li>
          <li><Icon name="globe" size={18} />{t.trust3}</li>
        </ul>
      </aside>

      <main className="ss-phone">
        <header className="ss-head">
          <div>
            <p className="ss-kicker">{t.title}</p>
            <h2>{t.formTitle}</h2>
          </div>
          <button className="ss-lang" onClick={toggleLang} aria-label="Switch language">
            <Icon name="globe" size={16} /> {lang === 'en' ? 'বাংলা' : 'English'}
          </button>
        </header>

        <p className="ss-label">{t.scenarios}</p>
        <div className="ss-chips" role="group" aria-label={t.scenarios}>
          {examples.map(x => (
            <button key={x.example_id} className={'ss-chip' + (picked === x.example_id ? ' on' : '')}
              onClick={() => loadExample(x.example_id)} title={x.title}>
              {t.ex?.[x.example_id] || x.title}
            </button>
          ))}
        </div>

        <div className="ss-form">
          <label className="ss-field"><span>{t.sender}</span>
            <div className="ss-input"><Icon name="user" size={18} />
              <input value={form.sender_id} onChange={e => setForm({ ...form, sender_id: e.target.value })} /></div>
          </label>
          <label className="ss-field"><span>{t.recipient}</span>
            <div className="ss-input"><Icon name="send" size={18} />
              <input value={form.recipient_id} onChange={e => setForm({ ...form, recipient_id: e.target.value })} /></div>
          </label>
          <label className="ss-field"><span>{t.amount}</span>
            <div className="ss-input amount"><b>৳</b>
              <input type="number" inputMode="numeric" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></div>
          </label>
        </div>

        <button className="ss-btn primary" disabled={busy} onClick={() => check()}>
          {busy ? <span className="spinner" /> : <Icon name="shield" size={20} />} {t.check}
        </button>

        {errText && <p className="ss-error" role="alert"><Icon name="alert" size={18} /> {errText}</p>}

        {res && !final && (
          <section className={'ss-result ' + kind} key={res.tx_ref}>
            <div className="ss-result-head">
              <span className="ss-result-icon"><Icon name={ICON[kind]} size={26} stroke={2.4} /></span>
              <div>
                <h3>{t[TITLE_KEY[kind]]}</h3>
                <p>{res.action === 'hold_for_review' ? t.held : res.message}</p>
              </div>
            </div>

            <div className="ss-meter" aria-label={`${t.score} ${score}`}>
              <div className="ss-meter-top"><span>{t.score}</span><b>{score}/100</b></div>
              <div className="ss-track"><div className={'ss-fill ' + kind} style={{ width: score + '%' }} /></div>
            </div>

            {res.action === 'hold_for_review' && (
              <p className="ss-waiting"><span className="spinner" /> {t.waiting}</p>
            )}

            {res.reasons?.length > 0 && (
              <ul className="ss-reasons">
                {res.reasons.map(r => (
                  <li key={r.code}><span className="ri"><Icon name={REASON_ICON[r.code] || 'alert'} size={18} /></span>{r.text}</li>
                ))}
              </ul>
            )}

            {canAct && (
              <div className="ss-actions">
                <button className={'ss-btn go ' + kind} disabled={left > 0} onClick={() => decide('proceed')}>
                  {left > 0 && <Ring value={left} total={total} size={40} />}
                  <span>{left > 0 ? `${t.sendAnyway} (${left})` : t.sendAnyway}</span>
                </button>
                <button className="ss-btn ghost" onClick={() => decide('cancel')}>{t.cancel}</button>
              </div>
            )}

            {res.action === 'warn_cooloff' && res.can_report && (
              <>
                <button className="ss-btn link" onClick={() => setShowReport(true)}><Icon name="flag" size={18} /> {t.report}</button>
                {showReport && <ReportForm t={t} form={form} txRef={res.tx_ref} />}
              </>
            )}
          </section>
        )}

        {final && (
          <section className={'ss-result final ' + (final === 'sent' || final === 'ok' ? 'low' : 'extreme')}>
            <div className="ss-done">
              <span className="ss-done-icon"><Icon name={final === 'sent' || final === 'ok' ? 'check' : 'x'} size={34} stroke={3} /></span>
              <h3>{t[final]}</h3>
            </div>
            <button className="ss-btn ghost" onClick={() => { reset(); setPicked(''); setForm({ sender_id: '', recipient_id: '', amount: '' }); setBase({}); }}>
              {t.again}
            </button>
          </section>
        )}
      </main>
    </div>
  );
}

function ReportForm({ t, form, txRef }) {
  const [note, setNote] = useState('');
  const [done, setDone] = useState(false);
  const [err, setErr] = useState(null);

  if (done) return <p className="ss-thanks"><Icon name="check" size={18} /> {t.thanks}</p>;

  const submit = () =>
    api.report({ sender_id: form.sender_id, recipient_id: form.recipient_id, tx_ref: txRef, note })
      .then(() => setDone(true))
      .catch(setErr);

  return (
    <div className="ss-report">
      <textarea rows={3} maxLength={300} placeholder={t.note} value={note} onChange={e => setNote(e.target.value)} />
      <button className="ss-btn primary small" onClick={submit}>{t.submit}</button>
      {err && <p className="ss-error">{friendly(err, t)}</p>}
    </div>
  );
}
