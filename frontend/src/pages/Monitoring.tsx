import { Card } from '../components/ui'

const GRAFANA = (import.meta.env.VITE_GRAFANA_URL as string | undefined) ?? 'http://localhost:3000'

export const DASHBOARDS: Array<{ uid: string; title: string; about: string }> = [
  { uid: 'rp-system-health', title: 'System health', about: 'Availability of every component at a glance' },
  { uid: 'rp-microservices', title: 'Microservices', about: 'Spring Boot request rate, latency, errors, JVM' },
  { uid: 'rp-cluster', title: 'Kubernetes cluster', about: 'Nodes, pods, restarts, resources' },
  { uid: 'rp-load-scalability', title: 'Load & scalability', about: 'Throughput, p95, HPA activity during k6 runs' },
  { uid: 'rp-high-availability', title: 'High availability', about: 'Replicas, pod failures, recovery' },
  { uid: 'rp-ml-inference', title: 'ML inference', about: 'Inference time, predictions per decision' },
  { uid: 'rp-model-performance', title: 'Model performance', about: 'Model version, review rate, drift signals' },
  { uid: 'rp-uncertainty', title: 'Uncertainty', about: 'Uncertainty distribution and human-review routing' },
  { uid: 'rp-errors-alerts', title: 'Errors & alerts', about: 'HTTP errors and firing alerts' },
  { uid: 'rp-security-posture', title: 'Security posture', about: 'Trivy Operator vulnerabilities and config audit' },
]

export function Monitoring() {
  return (
    <>
      <h1>Monitoring</h1>
      <p className="muted">Dashboards are provisioned as code in Grafana (Prometheus data source). Alerts are evaluated by Prometheus and routed by Alertmanager.</p>
      <div className="tiles">
        {DASHBOARDS.map((d) => (
          <Card key={d.uid} title={d.title}>
            <p className="muted small">{d.about}</p>
            <a href={`${GRAFANA}/d/${d.uid}`} target="_blank" rel="noopener noreferrer">Open in Grafana ↗</a>
          </Card>
        ))}
      </div>
    </>
  )
}
