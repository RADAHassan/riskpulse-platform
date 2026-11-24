# MLOps — MLflow pipeline & FastAPI serving (Tasks 5, 6)

| Folder | Content |
| :--- | :--- |
| `mlflow/` | Tracking server / registry configuration (backend store, artifact store) |
| `pipeline/` | Reproducible pipeline: Training → Evaluation → Statistical validation → Model Registry → Deployment |
| `serving/` | FastAPI service returning `prediction`, `probability`, `uncertainty`, `model_version` |

## Serving contract (consumed by `backend/risk-service`)

- `POST /predict` → `{ prediction, probability, uncertainty, decision, model_version }`
- `GET /health/live`, `GET /health/ready` (Kubernetes probes)
- `GET /metrics` (Prometheus: request count, latency histogram, inference time, uncertainty distribution)

The model code and artifacts come from [`ml/`](../ml/) (`ml/src/ml/predictor.py`, `ml/artifacts/`).
