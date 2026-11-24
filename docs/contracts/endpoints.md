# Endpoints

Public paths go through the gateway (`/api/**`). Roles: `ADMIN`, `ANALYST`, `CUSTOMER`.
"Owner" = the `customer_id` claim of the JWT equals the resource's customer (BOLA/IDOR protection, enforced in each service).
Errors: RFC 7807 `application/problem+json`, no stack trace.

## Public API

| Method & path | Service | Roles | Notes |
| :--- | :--- | :--- | :--- |
| `POST /api/auth/login` | auth | public | `{username,password}` → access + refresh token; lock after N failures |
| `POST /api/auth/refresh` | auth | public | refresh-token rotation, reuse detection |
| `POST /api/auth/logout` | auth | public (needs the refresh token) | revokes the refresh token |
| `GET /api/auth/me` | auth | authenticated | |
| `POST /api/auth/users` | auth | ADMIN | create user (role, optional `customerId`) |
| `GET/POST /api/customers`, `GET/PUT/DELETE /api/customers/{id}` | customer | list/create: staff; delete: ADMIN; read/update: staff or owner | |
| `POST /api/transactions` | transaction | CUSTOMER (own `customerId` only), ADMIN, ANALYST | persists, then calls risk-service |
| `GET /api/transactions`, `GET /api/transactions/{id}` | transaction | staff: all; CUSTOMER: own | |
| `POST /api/transactions/simulate` | transaction | ADMIN | `{count<=200, fraudRatio?}` replays demo transactions |
| `GET /api/reviews?status=OPEN` | risk | ADMIN, ANALYST | human review queue |
| `POST /api/reviews/{id}/resolve` | risk | ADMIN, ANALYST | `{resolution: APPROVE\|REJECT, note}` |
| `GET /api/risk/assessments/{transactionId}` | risk | staff, owner | |
| `GET /api/risk/stats` | risk | ADMIN, ANALYST | decision counters for the dashboard |
| `GET /api/notifications`, `POST /api/notifications/{id}/read` | notification | staff: all; CUSTOMER: own | |
| `GET /api/audit/events`, `GET /api/audit/events/verify` | audit | ADMIN, ANALYST (verify: ADMIN) | append-only, hash chained |
| `GET /api/ml/model/info`, `/api/ml/model/report`, `/api/ml/projections` | ml-serving (via gateway, key injected) | ADMIN, ANALYST | |
| `GET /openapi.yaml` | gateway | public | OpenAPI of the public API (used by ZAP API scan) |

## Internal API (not routed by the gateway)

Requires a valid JWT (propagated) **and** header `X-Service-Key`.

| Method & path | Service | Caller |
| :--- | :--- | :--- |
| `POST /internal/risk/assess` | risk | transaction |
| `POST /internal/audit/events` | audit | risk, transaction, auth |
| `POST /internal/notifications` | notification | risk |
| `PUT /internal/transactions/{id}/decision` | transaction | risk (review resolution) |

## ml-serving (FastAPI) — header `X-Service-Key` required except health/metrics

| Method & path | Notes |
| :--- | :--- |
| `POST /predict` | schema: `predict-request.schema.json` / `predict-response.schema.json` |
| `POST /predict/batch` | `{transactions:[...]}`, max `MAX_BATCH_SIZE` |
| `GET /model/info` | version, registry version, source (`mlflow` or `local-bundle`), policy |
| `GET /model/report` | benchmark, statistical tests, calibration, conformal summary (from `ml/artifacts`) |
| `GET /projections` | PCA/t-SNE/UMAP points (`latent_projections.json`) |
| `GET /health/live`, `GET /health/ready`, `GET /metrics` | no key |

## Decision semantics

`decision ∈ {APPROVE, HUMAN_REVIEW, DECLINE}`.
`DECLINE` requires a calibrated probability above the guard **and** a singleton conformal set `{FRAUD}` **and** low uncertainty.
Any uncertain prediction is capped at `HUMAN_REVIEW`. Any failure of ml-serving yields `HUMAN_REVIEW` (never `APPROVE`).
