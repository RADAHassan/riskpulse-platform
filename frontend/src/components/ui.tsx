import type { ReactNode } from 'react'
import type { Decision, TxStatus } from '../api/types'

const decisionClass: Record<string, string> = {
  APPROVE: 'ok',
  APPROVED: 'ok',
  HUMAN_REVIEW: 'warn',
  UNDER_REVIEW: 'warn',
  PENDING_RISK: 'warn',
  PENDING: 'muted',
  DECLINE: 'bad',
  DECLINED: 'bad',
  REJECTED: 'bad',
  OPEN: 'warn',
}

export function Badge({ value }: { value: Decision | TxStatus | string | null | undefined }) {
  if (!value) return <span className="badge muted">—</span>
  return <span className={`badge ${decisionClass[value] ?? 'muted'}`}>{value.replace('_', ' ')}</span>
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: 'ok' | 'warn' | 'bad' }) {
  return (
    <div className={`kpi ${tone ?? ''}`}>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  )
}

export function Loading({ what = 'data' }: { what?: string }) {
  return <p className="muted" role="status">Loading {what}…</p>
}

export function ErrorNote({ error }: { error?: string }) {
  return error ? <p className="error" role="alert">{error}</p> : null
}

export function UncertaintyBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  const tone = value >= 0.25 ? 'bad' : value >= 0.05 ? 'warn' : 'ok'
  return (
    <span className="ubar" title={`uncertainty ${value.toFixed(3)}`}>
      <span className={`ubar-fill ${tone}`} style={{ width: `${Math.min(100, value * 100)}%` }} />
      <span className="ubar-text">{value.toFixed(3)}</span>
    </span>
  )
}

export function Pager({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (p: number) => void }) {
  if (totalPages <= 1) return null
  return (
    <nav className="pager" aria-label="Pagination">
      <button onClick={() => onPage(page - 1)} disabled={page <= 0}>‹ Prev</button>
      <span>Page {page + 1} / {totalPages}</span>
      <button onClick={() => onPage(page + 1)} disabled={page + 1 >= totalPages}>Next ›</button>
    </nav>
  )
}
