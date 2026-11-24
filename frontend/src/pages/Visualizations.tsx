import { useMemo, useState } from 'react'
import { Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api } from '../api/client'
import type { ProjectionPoint, Projections } from '../api/types'
import { Card, ErrorNote, Loading } from '../components/ui'
import { num } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { buildSeries, summarize, uncertaintyOf, type ColorMode, type Projection } from '../lib/viz'

const PROJECTIONS: Array<{ id: Projection; label: string }> = [
  { id: 'pca', label: 'PCA' },
  { id: 'tsne', label: 't-SNE' },
  { id: 'umap', label: 'UMAP' },
]
const MODES: Array<{ id: ColorMode; label: string }> = [
  { id: 'class', label: 'True class' },
  { id: 'errors', label: 'Errors (FP / FN)' },
  { id: 'uncertainty', label: 'Uncertainty' },
  { id: 'review', label: 'Human review' },
]

export function Visualizations() {
  const { data, error, loading } = useAsync(() => api<Projections>('/api/ml/projections'), [])
  const [proj, setProj] = useState<Projection>('umap')
  const [mode, setMode] = useState<ColorMode>('class')
  const [onlyInteresting, setOnlyInteresting] = useState(false)

  const points = useMemo(() => {
    const all = data?.points ?? []
    return onlyInteresting ? all.filter((p) => p.true_label === 1 || p.human_review || p.is_fp || p.is_fn) : all
  }, [data, onlyInteresting])
  const series = useMemo(() => buildSeries(points, proj, mode), [points, proj, mode])
  const stats = useMemo(() => summarize(points), [points])
  const quality = data?.quality_metrics?.[proj]

  return (
    <>
      <h1>Latent-space visualizations</h1>
      <p className="muted">
        Stratified OOT sample projected with PCA, t-SNE and UMAP (Task 7). Explore class separation, outliers, model errors and where
        the model is uncertain.
      </p>
      <ErrorNote error={error} />
      {loading && !data && <Loading what="projections" />}
      {data && (
        <Card>
          <div className="row wrap">
            <div role="group" aria-label="Projection" className="seg">
              {PROJECTIONS.map((p) => (
                <button key={p.id} aria-pressed={proj === p.id} className={proj === p.id ? 'active' : ''} onClick={() => setProj(p.id)}>{p.label}</button>
              ))}
            </div>
            <div role="group" aria-label="Colour by" className="seg">
              {MODES.map((m) => (
                <button key={m.id} aria-pressed={mode === m.id} className={mode === m.id ? 'active' : ''} onClick={() => setMode(m.id)}>{m.label}</button>
              ))}
            </div>
            <label className="check">
              <input type="checkbox" checked={onlyInteresting} onChange={(e) => setOnlyInteresting(e.target.checked)} />
              Hide ordinary legitimate points
            </label>
          </div>
          <div className="chart" data-testid="scatter">
            <ResponsiveContainer width="100%" height={520}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <XAxis type="number" dataKey="x" name={`${proj}-1`} tick={{ fontSize: 11 }} />
                <YAxis type="number" dataKey="y" name={`${proj}-2`} tick={{ fontSize: 11 }} />
                <ZAxis range={[24, 24]} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<PointTooltip />} />
                <Legend />
                {series.map((s) => (
                  <Scatter key={s.name} name={`${s.name} (${s.points.length})`} data={s.points} fill={s.color} fillOpacity={0.75} isAnimationActive={false} />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="stats-row">
            <span>{stats.total} points</span><span>{stats.frauds} frauds</span><span>{stats.reviews} human-review</span>
            <span>{stats.falseNegatives} false negatives</span><span>{stats.falsePositives} false positives</span>
          </div>
          {quality && (
            <p className="muted small">
              {proj.toUpperCase()} quality — trustworthiness@15: {num(quality.trustworthiness_k15 as number, 3)}, silhouette (fraud vs legit): {num(quality.silhouette_fraud_vs_legit as number, 3)}
              {Array.isArray(quality.explained_variance_ratio) && <> · explained variance: {(quality.explained_variance_ratio as number[]).map((v) => `${(v * 100).toFixed(1)} %`).join(' / ')}</>}
            </p>
          )}
        </Card>
      )}
    </>
  )
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { p: ProjectionPoint } }> }) {
  const p = active ? payload?.[0]?.payload?.p : undefined
  if (!p) return null
  return (
    <div className="tooltip">
      <div><strong>{p.true_label === 1 ? 'Fraud' : 'Legitimate'}</strong> · OOT #{p.oot_index}</div>
      <div>P(fraud) {num(p.fraud_probability, 4)} · raw {num(p.raw_score, 4)}</div>
      <div>Uncertainty {num(uncertaintyOf(p), 3)}</div>
      <div>{p.human_review ? 'Routed to human review' : 'Automatic path'}{p.is_fn ? ' · missed fraud' : ''}{p.is_fp ? ' · false positive' : ''}</div>
    </div>
  )
}
