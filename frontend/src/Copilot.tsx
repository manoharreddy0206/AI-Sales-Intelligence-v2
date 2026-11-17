import React, { useState } from 'react';

type Evidence = { tool: string; input: any; status: string; result: any };
type Reply = {
  request_id: string; mode: string; model: string; status: string; answer: string; error: string | null;
  evidence: Evidence[]; citations: { source_id: string; title: string; source: string; text: string }[];
  dataset: { orders: number; first_date: string; last_date: string; as_of: string; name: string } | null;
  unverified_numbers: string[]; elapsed_ms: number;
};
type Turn = { question: string; reply?: Reply; failure?: string };

const SUGGESTIONS = ['What was revenue last month?', 'What changed versus the previous month?', 'How is a repeat customer defined?'];
const fmt = (v: number | null | undefined) => (v === null || v === undefined ? 'not defined' : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));
const pct = (v: number | null) => (v === null ? 'not defined' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);

function PeriodFigures({ r }: { r: any }) {
  return <>
    <p className="figure-head">{r.period.label} · {r.period.start} to {r.period.end}{r.period.partial ? ' · partial month' : ''}</p>
    <table><tbody>
      <tr><th>Revenue</th><td>{fmt(r.revenue)}</td></tr>
      <tr><th>Orders</th><td>{fmt(r.orders)}</td></tr>
      <tr><th>Customers</th><td>{fmt(r.customers)}</td></tr>
      <tr><th>Average order</th><td>{fmt(r.average_order)}</td></tr>
    </tbody></table>
  </>;
}

function Comparison({ r }: { r: any }) {
  const rows: [string, string][] = [['Revenue', 'revenue'], ['Orders', 'orders'], ['Average order', 'average_order']];
  return <table>
    <thead><tr><th></th><th>{r.current.period.label}</th><th>{r.previous.period.label}</th><th>Change</th><th>%</th></tr></thead>
    <tbody>{rows.map(([label, key]) => <tr key={key}>
      <th>{label}</th><td>{fmt(r.current[key])}</td><td>{fmt(r.previous[key])}</td>
      <td>{fmt(r.deltas[key].absolute)}</td><td title={r.deltas[key].note ?? ''}>{pct(r.deltas[key].percent)}</td>
    </tr>)}</tbody>
  </table>;
}

function EvidenceView({ e }: { e: Evidence }) {
  const r = e.result ?? {};
  if (e.tool === 'get_revenue_summary' && (r.status === 'ok' || r.status === 'empty_period')) return <PeriodFigures r={r} />;
  if (e.tool === 'compare_periods' && r.status === 'ok') return <Comparison r={r} />;
  if (e.tool === 'search_metric_glossary') return null; // shown as citations
  return <p className="muted">{e.tool}: {r.status}{r.message ? ` · ${r.message}` : ''}</p>;
}

export default function Copilot({ start, end }: { start: string; end: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    q = q.trim();
    if (!q || busy) return;
    setBusy(true); setQuestion('');
    const index = turns.length;
    setTurns(t => [...t, { question: q }]);
    try {
      const response = await fetch('/api/copilot', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question: q, context: { start: start || null, end: end || null } }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Copilot request failed');
      setTurns(t => t.map((turn, i) => (i === index ? { ...turn, reply: data } : turn)));
    } catch (err: any) {
      setTurns(t => t.map((turn, i) => (i === index ? { ...turn, failure: err.message || 'Could not reach the backend' } : turn)));
    } finally { setBusy(false); }
  }

  return <section className="panel copilot">
    <div className="heading"><h2>Sales Analyst Copilot</h2><small>Figures come from database tools · definitions from the metrics glossary</small></div>
    <div className="chips">{SUGGESTIONS.map(s => <button key={s} className="chip" disabled={busy} onClick={() => ask(s)}>{s}</button>)}</div>
    <div className="turns" aria-live="polite">
      {turns.map((t, i) => <div className="turn" key={i}>
        <p className="question">{t.question}</p>
        {!t.reply && !t.failure && <p className="muted">Thinking…</p>}
        {t.failure && <p className="warn">{t.failure}</p>}
        {t.reply && <div className="reply">
          <p className="badges">
            <span className={t.reply.mode === 'stub' ? 'badge stub' : 'badge'}>{t.reply.mode === 'stub' ? 'Stub mode · no LLM' : `LLM · ${t.reply.model}`}</span>
            <span className="badge plain">{t.reply.status}</span>
          </p>
          {t.reply.answer && <p>{t.reply.answer}</p>}
          {t.reply.error && <p className="warn">{t.reply.error}</p>}
          {t.reply.unverified_numbers.length > 0 && <p className="warn">Numbers in the text that do not match tool output: {t.reply.unverified_numbers.join(', ')}. Use the table below.</p>}
          {t.reply.evidence.some(e => e.tool !== 'search_metric_glossary') && <div className="evidence"><small>From the database</small>{t.reply.evidence.map((e, j) => <EvidenceView key={j} e={e} />)}</div>}
          {t.reply.citations.length > 0 && <div className="evidence"><small>Sources</small>{t.reply.citations.map(c => <blockquote key={c.source_id}><b>[{c.source_id}] {c.title}</b><br />{c.text}<br /><small>{c.source}</small></blockquote>)}</div>}
          <small className="muted">
            {t.reply.dataset ? `Dataset ${t.reply.dataset.name}: ${t.reply.dataset.orders} orders, ${t.reply.dataset.first_date} to ${t.reply.dataset.last_date}. Relative periods use ${t.reply.dataset.as_of}. ` : ''}
            Request {t.reply.request_id} · {t.reply.elapsed_ms} ms
          </small>
        </div>}
      </div>)}
    </div>
    <form className="toolbar" onSubmit={e => { e.preventDefault(); ask(question); }}>
      <input aria-label="Ask the copilot" placeholder="Ask about revenue, a period comparison, or a metric definition" maxLength={500} value={question} onChange={e => setQuestion(e.target.value)} />
      <button disabled={busy || !question.trim()}>{busy ? 'Working…' : 'Ask'}</button>
    </form>
  </section>;
}
