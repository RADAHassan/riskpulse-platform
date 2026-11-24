export type Role = 'ADMIN' | 'ANALYST' | 'CUSTOMER'
export type Decision = 'APPROVE' | 'HUMAN_REVIEW' | 'DECLINE'
export type TxStatus = 'PENDING' | 'APPROVED' | 'DECLINED' | 'UNDER_REVIEW' | 'PENDING_RISK'

export interface Page<T> {
  content: T[]
  page: number
  size: number
  totalElements: number
  totalPages: number
}

export interface TokenResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresIn: number
  username: string
  role: Role
  customerId: string | null
}

export interface Transaction {
  id: string
  customerId: string
  amount: number
  currency: string
  merchant: string | null
  status: TxStatus
  decision: Decision | null
  reason: string | null
  probability: number | null
  uncertainty: number | null
  modelVersion: string | null
  simulated: boolean
  createdAt: string
  decidedAt: string | null
}

export interface Assessment {
  transactionId: string
  decision: Decision
  reason: string
  probability: number | null
  uncertainty: number | null
  modelVersion: string | null
  registryVersion: string | null
  conformalSet: string | null
  fallback: boolean
}

export interface ReviewCase {
  id: string
  transactionId: string
  customerId: string
  amount: number
  probability: number | null
  uncertainty: number | null
  modelVersion: string | null
  reason: string
  status: 'OPEN' | 'APPROVED' | 'REJECTED'
  resolvedBy: string | null
  resolvedAt: string | null
  note: string | null
  createdAt: string
}

export interface Customer {
  id: string
  firstName: string
  lastName: string
  email: string
  country: string
  segment: 'STANDARD' | 'PREMIUM'
  createdAt: string
}

export interface AuditEvent {
  seq: number
  id: string
  occurredAt: string
  actor: string
  actorRole: string
  action: string
  resourceType: string
  resourceId: string
  decision: string | null
  modelVersion: string | null
  details: string
  hash: string
}

export interface RiskStats {
  decisions: Record<Decision, number>
  fallbacks: number
  openReviews: number
  mlCircuit: string
}

export interface SimulationSummary {
  requested: number
  processed: number
  approved: number
  humanReview: number
  declined: number
  failed: number
}

export interface ModelInfo {
  model_version: string
  registry_version: string | null
  model_source: 'mlflow' | 'local-bundle'
  model_uri: string
  alias: string | null
  loaded_at: string
  policy: Record<string, number | string | boolean>
  decision_semantics: Record<string, string>
}

export interface ModelReport {
  benchmark: Array<Record<string, number | string>>
  statistical_tests: Array<Record<string, number | string | boolean>>
  friedman: Record<string, { chi2: number; p_value: number; df: number }> & Record<string, unknown>
  statistical_summary: Record<string, unknown>
  calibration: Array<{ model: string; brier_raw: number; brier_calibrated: number }>
  conformal: Record<string, Record<string, number | string>>
  conformal_windows: Array<Record<string, number | string>>
  figures: string[]
}

export interface ProjectionPoint {
  oot_index: number
  true_label: 0 | 1
  raw_score: number
  fraud_probability: number
  human_review: boolean
  is_fp: boolean
  is_fn: boolean
  pca_x: number
  pca_y: number
  tsne_x: number
  tsne_y: number
  umap_x: number
  umap_y: number
}

export interface Projections {
  metadata: Record<string, unknown>
  quality_metrics: Record<string, Record<string, number | number[]>>
  points: ProjectionPoint[]
}

export interface AuditVerification {
  valid: boolean
  checked: number
  firstBrokenSeq: number | null
  reason: string | null
}
