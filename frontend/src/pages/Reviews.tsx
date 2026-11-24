import { useState } from 'react'
import { api } from '../api/client'
import type { Page, ReviewCase } from '../api/types'
import { Badge, Card, ErrorNote, Loading, Pager, UncertaintyBar } from '../components/ui'
import { money, num, shortId, when } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function Reviews() {
  const [page, setPage] = useState(0)
  const [status, setStatus] = useState<'OPEN' | 'APPROVED' | 'REJECTED'>('OPEN')
  const { data, error, loading, reload } = useAsync(
    () => api<Page<ReviewCase>>(`/api/reviews?status=${status}&page=${page}&size=10`),
    [status, page],
  )
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [actionError, setActionError] = useState<string>()
  const [busyId, setBusyId] = useState<string>()

  async function resolve(id: string, resolution: 'APPROVE' | 'REJECT') {
    setBusyId(id)
    setActionError(undefined)
    try {
      await api(`/api/reviews/${id}/resolve`, { method: 'POST', json: { resolution, note: notes[id] || undefined } })
      reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not resolve the case')
    } finally {
      setBusyId(undefined)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Human review queue</h1>
        <div className="row">
          <select aria-label="Case status" value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setPage(0) }}>
            <option>OPEN</option><option>APPROVED</option><option>REJECTED</option>
          </select>
          <button onClick={reload}>Refresh</button>
        </div>
      </div>
      <p className="muted">
        Uncertain or high-risk predictions are never declined automatically: an analyst decides here. Every resolution is written to the audit trail.
      </p>
      <ErrorNote error={error ?? actionError} />
      <Card>
        {loading && !data ? <Loading what="review cases" /> : (
          <table>
            <thead>
              <tr><th>Transaction</th><th>Amount</th><th>P(fraud)</th><th>Uncertainty</th><th>Model</th><th>Reason</th><th>Created</th><th>{status === 'OPEN' ? 'Decision' : 'Outcome'}</th></tr>
            </thead>
            <tbody>
              {data?.content.map((c) => (
                <tr key={c.id}>
                  <td title={c.transactionId}>{shortId(c.transactionId)}</td>
                  <td className="num">{money(c.amount)}</td>
                  <td className="num">{num(c.probability)}</td>
                  <td><UncertaintyBar value={c.uncertainty} /></td>
                  <td className="small">{c.modelVersion ?? '—'}</td>
                  <td className="small">{c.reason}</td>
                  <td>{when(c.createdAt)}</td>
                  <td>
                    {c.status === 'OPEN' ? (
                      <div className="row">
                        <input aria-label={`Note for ${shortId(c.transactionId)}`} placeholder="note" maxLength={500} value={notes[c.id] ?? ''} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} />
                        <button className="ok" disabled={busyId === c.id} onClick={() => resolve(c.id, 'APPROVE')}>Approve</button>
                        <button className="bad" disabled={busyId === c.id} onClick={() => resolve(c.id, 'REJECT')}>Reject</button>
                      </div>
                    ) : (
                      <span><Badge value={c.status} /> <span className="muted small">by {c.resolvedBy}</span></span>
                    )}
                  </td>
                </tr>
              ))}
              {data?.content.length === 0 && <tr><td colSpan={8} className="muted center">Nothing to review.</td></tr>}
            </tbody>
          </table>
        )}
        <Pager page={page} totalPages={data?.totalPages ?? 0} onPage={setPage} />
      </Card>
    </>
  )
}
