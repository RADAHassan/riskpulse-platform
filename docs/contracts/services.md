# Services, ports, images, configuration

Images: `ghcr.io/radahassan/riskpulse-<service>:<short-sha>` (never `latest`, enforced by Kyverno).
All containers run as non-root (UID 10001), with a read-only root filesystem (`/tmp` is an `emptyDir`).

| Service | Container port | Image name | Database | Probes |
| :--- | :---: | :--- | :--- | :--- |
| `api-gateway` | 8080 | `riskpulse-api-gateway` | – | `/actuator/health/{liveness,readiness}` |
| `auth-service` | 8081 | `riskpulse-auth-service` | `auth` | same |
| `customer-service` | 8082 | `riskpulse-customer-service` | `customer` | same |
| `transaction-service` | 8083 | `riskpulse-transaction-service` | `transaction` | same |
| `risk-service` | 8084 | `riskpulse-risk-service` | `risk` | same |
| `notification-service` | 8085 | `riskpulse-notification-service` | `notification` | same |
| `audit-service` | 8086 | `riskpulse-audit-service` | `audit` | same |
| `ml-serving` (FastAPI) | 8000 | `riskpulse-ml-serving` | – | `/health/live`, `/health/ready` |
| `frontend` (nginx-unprivileged) | 8080 | `riskpulse-frontend` | – | `/` |
| `mlflow` | 5000 | `riskpulse-mlflow` | `mlflow` | `/health` |
| `postgres` | 5432 | `postgres:17-alpine` (pinned by digest) | one DB per service | `pg_isready` |

Local host ports (Docker Compose): frontend `5173`, gateway `8080`, ml-serving `8000`, MLflow `5000`,
Prometheus `9090`, Grafana `3000`, Alertmanager `9093`, PostgreSQL `5432` (bound to `127.0.0.1`).

Spring services expose `/actuator/health/**` and `/actuator/prometheus` on the **service port**.
These paths are never routed by the gateway and are only reachable inside the cluster/compose network
(NetworkPolicy: only Prometheus and the kubelet probes).

## Environment variables

### Common (all Spring services)

| Variable | Meaning |
| :--- | :--- |
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://postgres:5432/<db>` |
| `SPRING_DATASOURCE_USERNAME` / `SPRING_DATASOURCE_PASSWORD` | Per-service DB role (least privilege, one role per database) |
| `JWT_ISSUER` | `riskpulse-auth` |
| `JWT_JWKS_URI` | `http://auth-service:8081/.well-known/jwks.json` (resource servers) |
| `SERVICE_KEY` | Shared key for `/internal/**` calls (header `X-Service-Key`) |
| `JAVA_TOOL_OPTIONS` | `-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError` |

### auth-service

`JWT_PRIVATE_KEY` (PKCS#8 PEM, base64), `JWT_PUBLIC_KEY` (X.509 PEM, base64), `JWT_PREVIOUS_PUBLIC_KEY` (optional, rotation),
`JWT_KEY_ID`, `JWT_ACCESS_TTL` (default `PT15M`), `JWT_REFRESH_TTL` (default `P7D`),
`LOGIN_MAX_FAILURES` (default 5), `LOGIN_LOCK_MINUTES` (default 15),
`SEED_ADMIN_USERNAME`/`SEED_ADMIN_PASSWORD`, `SEED_ANALYST_USERNAME`/`SEED_ANALYST_PASSWORD`.
If `JWT_PRIVATE_KEY` is absent the service generates an ephemeral key **only** with profile `dev`; it refuses to start otherwise.

### api-gateway

`CORS_ALLOWED_ORIGINS`, `RATE_LIMIT_IP_PER_MIN` (default 300), `RATE_LIMIT_USER_PER_MIN` (default 600),
`MAX_REQUEST_BYTES` (default 1048576), `ML_SERVING_URL`, `SERVICE_KEY` (injected towards ml-serving only),
`<SERVICE>_URL` for each downstream service.

### risk-service

`ML_SERVING_URL`, `ML_SERVING_TIMEOUT_MS` (default 1500), `AUDIT_SERVICE_URL`, `NOTIFICATION_SERVICE_URL`,
`TRANSACTION_SERVICE_URL`, `RISK_UNCERTAINTY_REVIEW_THRESHOLD` (default 0.25).

### transaction-service

`RISK_SERVICE_URL`, `SIMULATOR_MAX_COUNT` (default 200).

### ml-serving

`SERVICE_KEY`, `MLFLOW_TRACKING_URI` (optional), `MODEL_URI` (default `models:/riskpulse-fraud@champion`),
`LOCAL_BUNDLE_PATH`, `LOCAL_CONFORMAL_PATH`, `MAX_BATCH_SIZE` (default 256), `ARTIFACTS_DIR`.

### frontend (build time)

`VITE_API_BASE_URL` (gateway), `VITE_GRAFANA_URL`.

## Databases

One PostgreSQL instance, databases `auth`, `customer`, `transaction`, `risk`, `notification`, `audit`, `mlflow`,
each owned by a dedicated role `<db>_user` (password from `POSTGRES_<DB>_PASSWORD`). Flyway owns the schema.
