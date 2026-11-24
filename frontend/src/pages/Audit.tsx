import { useState } from 'react'
import { api } from '../api/client'
import type { AuditEvent, AuditVerification, Page } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Badge, Card, ErrorNote, Loading, Pager } from '../components/ui'
import { shortId, when } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function Audit() {
  const { hasRole } = useAuth()
  const [page, setPage] = useState(0)
  const [action, setAction] = useState('')
  const [resourceId, setResourceId] = useState('')
  const query = `page=${page}&size=25${action ? `&action=${encodeURIComponent(action)}` : ''}${resourceId ? `&resourceId=${encodeURIComponent(resourceId)}` : ''}`
  const { data, error, loading, reload } = useAsync(() => api<Page<AuditEvent>>(`/api/audit/events?${query}`), [query])
  const [verification, setVerification] = useState<AuditVerification>()
  const [verifyError, setVerifyError] = useState<string>()

  async function verify() {
    setVerifyError(undefined)
    try {
      setVerification(await api<AuditVerification>('/api/audit/events/verify'))
    } catch (err) {
      setVerifyError(err instanceof Error ? err.message : 'Verification failed')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Audit trail</h1>
        <div className="row">
          {hasRole('ADMIN') && <button onClick={verify}>Verify hash chain</button>}
          <button onClick={reload}>Refresh</button>
        </div>
      </div>
      <p className="muted">Append-only, hash-chained log of every decision (with the model version), review and security event.</p>
      <ErrorNote error={error ?? verifyError} />
      {verification && (
        <p role="status" className={verification.valid ? 'ok-text' : 'error'}>
          {verification.valid
            ? `Chain intact: ${verification.checked} events verified.`
            : `Chain BROKEN at #${verification.firstBrokenSeq}: ${verification.reason}`}
        </p>
      )}
      <Card>
        <div className="row">
          <input aria-label="Action filter" placeholder="Action (e.g. RISK_DECISION)" value={action} onChange={(e) => { setAction(e.target.value); setPage(0) }} />
          <input aria-label="Resource filter" placeholder="Resource id" value={resourceId} onChange={(e) => { setResourceId(e.target.value); setPage(0) }} />
        </div>
        {loading && !data ? <Loading what="audit events" /> : (
          <table>
            <thead><tr><th>#</th><th>When</th><th>Actor</th><th>Action</th><th>Resource</th><th>Decision</th><th>Model</th><th>Hash</th></tr></thead>
            <tbody>
              {data?.content.map((e) => (
                <tr key={e.id} title={e.details}>
                  <td>{e.seq}</td><td>{when(e.occurredAt)}</td><td>{e.actor} <span className="muted small">{e.actorRole}</span></td>
                  <td>{e.action}</td><td>{e.resourceType} {shortId(e.resourceId)}</td>
                  <td>{e.decision ? <Badge value={e.decision} /> : '—'}</td>
                  <td className="small">{e.modelVersion ?? '—'}</td><td className="small mono">{e.hash.slice(0, 10)}…</td>
                </tr>
              ))}
              {data?.content.length === 0 && <tr><td colSpan={8} className="muted center">No events.</td></tr>}
            </tbody>
          </table>
        )}
        <Pager page={page} totalPages={data?.totalPages ?? 0} onPage={setPage} />
      </Card>
    </>
  )
}
