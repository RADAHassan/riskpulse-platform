import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ModelInfo, Page, RiskStats, Transaction } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Card, ErrorNote, Kpi, Loading } from '../components/ui'
import { pct } from '../lib/format'
import { useAsync } from '../lib/useAsync'

interface Overview {
  total: number
  stats: RiskStats | null
  model: ModelInfo | null
}

export function Dashboard() {
  const { user, hasRole } = useAuth()
  const staff = hasRole('ADMIN', 'ANALYST')
  const { data, error, loading, reload } = useAsync<Overview>(async () => {
    const total = (await api<Page<Transaction>>('/api/transactions?size=1')).totalElements
    if (!staff) return { total, stats: null, model: null }
    const [stats, model] = await Promise.all([api<RiskStats>('/api/risk/stats'), api<ModelInfo>('/api/ml/model/info')])
    return { total, stats, model }
  }, [staff])

  if (loading && !data) return <Loading what="dashboard" />
  const stats = data?.stats
  const decided = stats ? stats.decisions.APPROVE + stats.decisions.HUMAN_REVIEW + stats.decisions.DECLINE : 0
  const reviewRate = stats && decided > 0 ? stats.decisions.HUMAN_REVIEW / decided : null

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        <button onClick={reload}>Refresh</button>
      </div>
      <ErrorNote error={error} />
      <div className="kpis">
        <Kpi label="Transactions" value={data?.total ?? '—'} />
        {stats && (
          <>
            <Kpi label="Approved" value={stats.decisions.APPROVE} tone="ok" />
            <Kpi label="Sent to human review" value={stats.decisions.HUMAN_REVIEW} hint={`${pct(reviewRate)} of decisions`} tone="warn" />
            <Kpi label="Declined" value={stats.decisions.DECLINE} tone="bad" />
            <Kpi label="Open reviews" value={stats.openReviews} tone={stats.openReviews > 0 ? 'warn' : 'ok'} />
            <Kpi label="ML fallbacks" value={stats.fallbacks} hint="ml-serving unavailable → human review" tone={stats.fallbacks > 0 ? 'warn' : 'ok'} />
            <Kpi label="ML circuit" value={stats.mlCircuit} tone={stats.mlCircuit === 'CLOSED' ? 'ok' : 'bad'} />
          </>
        )}
      </div>
      {data?.model && (
        <Card title="Served model">
          <dl className="grid">
            <dt>Version</dt><dd>{data.model.model_version}</dd>
            <dt>Registry</dt><dd>v{data.model.registry_version ?? '—'} ({data.model.alias ?? 'no alias'}) via {data.model.model_source}</dd>
            <dt>Decline rule</dt><dd>{data.model.decision_semantics.DECLINE}</dd>
          </dl>
        </Card>
      )}
      {staff && stats && stats.openReviews > 0 && (
        <Card>
          <p>
            <strong>{stats.openReviews}</strong> transaction(s) are waiting for a human decision. <Link to="/reviews">Open the review queue →</Link>
          </p>
        </Card>
      )}
      {!staff && <Card><p className="muted">Signed in as {user?.username}. You can see your own transactions and profile.</p></Card>}
    </>
  )
}
