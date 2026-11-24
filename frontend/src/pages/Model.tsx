import { useEffect, useState } from 'react'
import { api, apiBlobUrl } from '../api/client'
import type { ModelInfo, ModelReport } from '../api/types'
import { Card, ErrorNote, Loading } from '../components/ui'
import { useAsync } from '../lib/useAsync'

const fmt = (v: unknown, d = 4): string => (typeof v === 'number' ? v.toFixed(d) : String(v ?? '—'))

export function Model() {
  const info = useAsync(() => api<ModelInfo>('/api/ml/model/info'), [])
  const report = useAsync(() => api<ModelReport>('/api/ml/model/report'), [])
  const r = report.data
  const serving = r?.conformal?.serving_oot_evaluation
  const pooled = r?.conformal?.pooled_oot

  return (
    <>
      <h1>Model</h1>
      <ErrorNote error={info.error ?? report.error} />
      {info.data && (
        <Card title="Served model">
          <dl className="grid">
            <dt>Model version</dt><dd>{info.data.model_version}</dd>
            <dt>MLflow registry</dt><dd>{info.data.model_uri} → v{info.data.registry_version ?? '—'} ({info.data.model_source})</dd>
            <dt>Loaded at</dt><dd>{info.data.loaded_at}</dd>
            <dt>Auto-decline guard</dt><dd>p ≥ {fmt(info.data.policy.auto_decline_prob_guard, 2)} and uncertainty &lt; {fmt(info.data.policy.uncertainty_review_threshold, 2)}</dd>
            <dt>Conformal quantiles</dt><dd>q_legit = {fmt(info.data.policy.conformal_q_legit, 5)}, q_fraud = {fmt(info.data.policy.conformal_q_fraud, 5)}</dd>
            {Object.entries(info.data.decision_semantics).map(([k, v]) => (<span key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></span>))}
          </dl>
        </Card>
      )}
      {report.loading && !r && <Loading what="model report" />}
      {r && (
        <>
          <Card title="Benchmark — 10 expanding chronological OOT windows">
            <table>
              <thead><tr><th>Model</th><th>PR-AUC</th><th>95 % CI (windows)</th><th>ROC-AUC</th><th>F1 @0.20 %</th><th>MCC @0.20 %</th><th>Latency (1 txn, ms)</th></tr></thead>
              <tbody>
                {r.benchmark.map((b) => (
                  <tr key={String(b.Model)}>
                    <td>{String(b.Model)}</td><td className="num">{fmt(b['PR-AUC'])}</td>
                    <td className="num">[{fmt(b['PR-AUC_Window_95CI_Low'])}, {fmt(b['PR-AUC_Window_95CI_High'])}]</td>
                    <td className="num">{fmt(b['ROC-AUC'])}</td><td className="num">{fmt(b['F1@0.20%'])}</td>
                    <td className="num">{fmt(b['MCC@0.20%'])}</td><td className="num">{fmt(b['Single_Txn_Latency_ms'])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Statistical validation">
            <p>
              Friedman omnibus (5 models, df = {fmt(r.friedman.friedman_5_models?.df, 0)}): χ² = {fmt(r.friedman.friedman_5_models?.chi2, 2)}, p = {fmt(r.friedman.friedman_5_models?.p_value, 6)}.
              Without SVM (df = {fmt(r.friedman.friedman_4_models_no_svm?.df, 0)}): χ² = {fmt(r.friedman.friedman_4_models_no_svm?.chi2, 2)}, p = {fmt(r.friedman.friedman_4_models_no_svm?.p_value, 4)}.
            </p>
            <table>
              <thead><tr><th>Comparison</th><th>Mean PR-AUC (XGB / other)</th><th>Wilcoxon p</th><th>Holm-adj. p</th><th>Cliff's δ</th><th>Significant</th></tr></thead>
              <tbody>
                {r.statistical_tests.map((t) => (
                  <tr key={String(t.Comparison)}>
                    <td>{String(t.Comparison)}</td>
                    <td className="num">{fmt(t.XGBoost_Mean_PR_AUC)} / {fmt(t.Other_Mean_PR_AUC)}</td>
                    <td className="num">{fmt(t.raw_p_value, 5)}</td><td className="num">{fmt(t.adjusted_p_value, 5)}</td>
                    <td className="num">{fmt(t.Cliffs_Delta, 2)}</td><td>{String(t['Significant (alpha=0.05)'])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Calibration (isotonic) — Brier score">
            <table>
              <thead><tr><th>Model</th><th>Brier raw</th><th>Brier calibrated</th><th>Improvement</th></tr></thead>
              <tbody>
                {r.calibration.map((c) => (
                  <tr key={c.model}>
                    <td>{c.model}</td><td className="num">{fmt(c.brier_raw, 6)}</td><td className="num">{fmt(c.brier_calibrated, 6)}</td>
                    <td className="num">{c.brier_raw > 0 ? `${(((c.brier_raw - c.brier_calibrated) / c.brier_raw) * 100).toFixed(1)} %` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Figure name="reliability" caption="Reliability diagram (disjoint OOT)" />
          </Card>
          <Card title="Uncertainty — Mondrian conformal prediction">
            <dl className="grid">
              <dt>Method</dt><dd>{String(r.conformal.method ?? '—')}</dd>
              {serving && (<>
                <dt>Served block (n = {fmt(serving.n_test, 0)})</dt>
                <dd>legit coverage {fmt(serving.empirical_coverage_legit)} · fraud coverage {fmt(serving.empirical_coverage_fraud)} · reviews {fmt(serving.conformal_review_count, 0)} ({fmt(serving.conformal_review_rate_pct, 3)} %)</dd>
              </>)}
              {pooled && (<>
                <dt>Pooled OOT (n = {fmt(pooled.total_txns, 0)})</dt>
                <dd>legit coverage {fmt(pooled.empirical_coverage_legit)} · fraud coverage {fmt(pooled.empirical_coverage_fraud)} · review rate {fmt(pooled.human_review_rate_pct, 3)} %</dd>
              </>)}
            </dl>
            <Figure name="pr_curves" caption="Precision–recall curves (pooled disjoint OOT)" />
          </Card>
        </>
      )}
    </>
  )
}

function Figure({ name, caption }: { name: string; caption: string }) {
  const [src, setSrc] = useState<string>()
  const [error, setError] = useState(false)
  useEffect(() => {
    let url: string | undefined
    let cancelled = false
    apiBlobUrl(`/api/ml/model/figures/${name}`)
      .then((u) => {
        url = u
        if (!cancelled) setSrc(u)
      })
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [name])
  if (error) return null
  return src ? <figure><img src={src} alt={caption} className="figure" /><figcaption className="muted small">{caption}</figcaption></figure> : null
}
