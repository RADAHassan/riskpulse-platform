import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Assessment, Page, SimulationSummary, Transaction, TxStatus } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Badge, Card, ErrorNote, Loading, Pager, UncertaintyBar } from '../components/ui'
import { money, num, parseFeatures, shortId, when } from '../lib/format'
import { useAsync } from '../lib/useAsync'

const STATUSES: TxStatus[] = ['PENDING', 'APPROVED', 'DECLINED', 'UNDER_REVIEW', 'PENDING_RISK']

export function Transactions() {
  const { hasRole, user } = useAuth()
  const staff = hasRole('ADMIN', 'ANALYST')
  const [page, setPage] = useState(0)
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const { data, error, loading, reload } = useAsync(
    () => api<Page<Transaction>>(`/api/transactions?page=${page}&size=15${status ? `&status=${status}` : ''}`),
    [page, status],
  )

  return (
    <>
      <div className="page-head">
        <h1>Transactions</h1>
        <div className="row">
          <select aria-label="Status filter" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0) }}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <button onClick={reload}>Refresh</button>
        </div>
      </div>
      <ErrorNote error={error} />
      <Card>
        {loading && !data ? <Loading what="transactions" /> : (
          <table>
            <thead>
              <tr><th>ID</th><th>Customer</th><th>Amount</th><th>Status</th><th>P(fraud)</th><th>Uncertainty</th><th>Created</th></tr>
            </thead>
            <tbody>
              {data?.content.map((t) => (
                <tr key={t.id} onClick={() => setSelected(t.id)} className={selected === t.id ? 'selected clickable' : 'clickable'}>
                  <td title={t.id}>{shortId(t.id)}{t.simulated && <span className="tag">sim</span>}</td>
                  <td>{shortId(t.customerId)}</td>
                  <td className="num">{money(t.amount, t.currency)}</td>
                  <td><Badge value={t.status} /></td>
                  <td className="num">{num(t.probability)}</td>
                  <td><UncertaintyBar value={t.uncertainty} /></td>
                  <td>{when(t.createdAt)}</td>
                </tr>
              ))}
              {data?.content.length === 0 && <tr><td colSpan={7} className="muted center">No transactions yet.</td></tr>}
            </tbody>
          </table>
        )}
        <Pager page={page} totalPages={data?.totalPages ?? 0} onPage={setPage} />
      </Card>
      {selected && <TransactionDetail id={selected} staff={staff} onClose={() => setSelected(null)} />}
      <SubmitForm defaultCustomerId={user?.customerId ?? ''} staff={staff} onDone={reload} />
      {hasRole('ADMIN') && <SimulatorPanel onDone={reload} />}
    </>
  )
}

function TransactionDetail({ id, staff, onClose }: { id: string; staff: boolean; onClose: () => void }) {
  const tx = useAsync(() => api<Transaction>(`/api/transactions/${id}`), [id])
  const assessment = useAsync(() => (staff ? api<Assessment>(`/api/risk/assessments/${id}`) : Promise.resolve(null)), [id, staff])
  const t = tx.data
  return (
    <Card title={`Transaction ${shortId(id)}`} actions={<button className="link" onClick={onClose}>Close</button>}>
      <ErrorNote error={tx.error} />
      {t && (
        <dl className="grid">
          <dt>Status</dt><dd><Badge value={t.status} /> {t.reason && <span className="muted small">({t.reason})</span>}</dd>
          <dt>Amount</dt><dd>{money(t.amount, t.currency)} {t.merchant && <>at {t.merchant}</>}</dd>
          <dt>Calibrated probability</dt><dd>{num(t.probability, 6)}</dd>
          <dt>Uncertainty</dt><dd><UncertaintyBar value={t.uncertainty} /></dd>
          <dt>Model version</dt><dd>{t.modelVersion ?? '—'}</dd>
          <dt>Decided</dt><dd>{when(t.decidedAt)}</dd>
        </dl>
      )}
      {assessment.data && (
        <dl className="grid">
          <dt>Conformal set</dt><dd>{assessment.data.conformalSet ?? '—'}</dd>
          <dt>Registry version</dt><dd>{assessment.data.registryVersion ?? '—'}</dd>
          <dt>Fallback used</dt><dd>{assessment.data.fallback ? 'yes (ML unavailable → human review)' : 'no'}</dd>
        </dl>
      )}
    </Card>
  )
}

function SubmitForm({ defaultCustomerId, staff, onDone }: { defaultCustomerId: string; staff: boolean; onDone: () => void }) {
  const [customerId, setCustomerId] = useState(defaultCustomerId)
  const [amount, setAmount] = useState('49.90')
  const [merchant, setMerchant] = useState('')
  const [features, setFeatures] = useState(Array(28).fill('0').join(', '))
  const [result, setResult] = useState<Transaction>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(undefined)
    setResult(undefined)
    try {
      const parsed = parseFeatures(features)
      if (parsed.length !== 28) throw new Error(`Expected 28 features (V1..V28), got ${parsed.length}`)
      const body = { customerId: customerId || undefined, amount: Number(amount), merchant: merchant || undefined, features: parsed }
      setResult(await api<Transaction>('/api/transactions', { method: 'POST', json: body }))
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Submit a transaction">
      <form onSubmit={submit} className="form">
        {staff && (
          <label>Customer ID<input value={customerId} onChange={(e) => setCustomerId(e.target.value)} placeholder="uuid" required /></label>
        )}
        <label>Amount<input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required /></label>
        <label>Merchant<input value={merchant} onChange={(e) => setMerchant(e.target.value)} maxLength={100} /></label>
        <label className="wide">Features V1..V28<textarea value={features} onChange={(e) => setFeatures(e.target.value)} rows={3} /></label>
        <div className="row">
          <button type="submit" disabled={busy}>{busy ? 'Scoring…' : 'Submit'}</button>
        </div>
      </form>
      <ErrorNote error={error} />
      {result && (
        <p role="status">
          Decision: <Badge value={result.decision} /> — status <Badge value={result.status} /> (probability {num(result.probability)}, uncertainty {num(result.uncertainty)})
        </p>
      )}
    </Card>
  )
}

function SimulatorPanel({ onDone }: { onDone: () => void }) {
  const [count, setCount] = useState(20)
  const [fraudRatio, setFraudRatio] = useState(0.2)
  const [summary, setSummary] = useState<SimulationSummary>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    setError(undefined)
    try {
      setSummary(await api<SimulationSummary>('/api/transactions/simulate', { method: 'POST', json: { count, fraudRatio } }))
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Simulator (admin)">
      <p className="muted small">Replays demo payloads through the full pipeline: transaction → risk → ml-serving → decision.</p>
      <div className="row">
        <label>Count<input type="number" min={1} max={200} value={count} onChange={(e) => setCount(Number(e.target.value))} /></label>
        <label>Fraud ratio<input type="number" min={0} max={1} step={0.05} value={fraudRatio} onChange={(e) => setFraudRatio(Number(e.target.value))} /></label>
        <button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run simulator'}</button>
      </div>
      <ErrorNote error={error} />
      {summary && (
        <p role="status">
          {summary.processed}/{summary.requested} processed — <Badge value="APPROVE" /> {summary.approved} · <Badge value="HUMAN_REVIEW" /> {summary.humanReview} · <Badge value="DECLINE" /> {summary.declined}
          {summary.failed > 0 && <> · failed {summary.failed}</>}
        </p>
      )}
    </Card>
  )
}
