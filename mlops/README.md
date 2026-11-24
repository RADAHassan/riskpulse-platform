# MLOps — MLflow pipeline & FastAPI serving (Tasks 5, 6)

| Folder | Content |
| :--- | :--- |
| [`mlflow/`](mlflow/) | MLflow server image (PostgreSQL backend store, proxied artifact store) |
| [`pipeline/`](pipeline/) | Training → Evaluation → Statistical validation → Model Registry → Deployment |
| [`serving/`](serving/) | FastAPI service: `prediction`, `probability`, `uncertainty`, `decision`, `model_version` |

## Pipeline (`pipeline/run_pipeline.py`)

```
train ─► evaluate ─► validate (statistical gates) ─► register (riskpulse-fraud) ─► deploy (reload ml-serving)
```

Each stage is a nested MLflow run under one parent run (experiment `riskpulse-fraud`).

| Stage | Script | Logs to MLflow |
| :--- | :--- | :--- |
| Training | `train.py` | XGBoost + policy parameters, bundle SHA-256, the bundle itself. **`train` mode** (dataset present) retrains the canonical 29D bundle; **`import` mode** (dataset absent) logs the shipped bundle without retraining |
| Evaluation | `evaluate.py` | PR-AUC, ROC-AUC, F1, MCC, Brier (raw / calibrated), ECE/BSS, latency, per-model metrics, figures, benchmark table |
| Statistical validation | `validate_stats.py` | Friedman, Wilcoxon-Holm p-values, Cliff's delta, gates G1–G5, `conformal.json` |
| Registry | `register.py` | pyfunc model (bundle + conformal quantiles as artifacts), version tags, alias `champion` **only if all gates pass** (else `challenger`) |
| Deployment | `deploy.py` | `POST /model/reload` on ml-serving, then checks it serves the new registry version |

Promotion gates (explicit thresholds, in `validate_stats.py`): G1 no competitor significantly better than XGBoost (Holm α = 0.05),
G2 isotonic calibration improves Brier, G3 conformal coverage on the served block (legit ≥ 0.99, fraud ≥ 0.80),
G4 single-transaction latency ≤ 1 ms, G5 omnibus Friedman test on record.
Numbers come from `ml/artifacts/*` and `ml/README.md` (copied verbatim into `pipeline/reference_metrics.json`); they are never recomputed in import mode.

```powershell
# from the repo root, ML virtualenv active (ml/.venv)
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
$env:SERVING_URL = "http://localhost:8000"; $env:SERVICE_KEY = "<service key>"
python mlops/pipeline/run_pipeline.py --mode import        # or --mode train when ml/data/creditcard.csv exists
cd mlops/pipeline && pytest                                 # unit + integration tests (local SQLite MLflow)
```

> Windows note: SQLAlchemy 2.1's C extension can be blocked by Application Control policies; `sqlalchemy<2.1` is pinned for local runs.

## Serving (`serving/`)

Loads `models:/riskpulse-fraud@champion` from MLflow (falls back to the local bundle if the registry is unreachable)
and exposes the contract in [`docs/contracts`](../docs/contracts/). Every response carries `model_version`,
`registry_version` and `model_source`.

| Endpoint | Auth |
| :--- | :--- |
| `POST /predict`, `POST /predict/batch` | `X-Service-Key` |
| `GET /model/info`, `GET /model/report`, `GET /model/figures/{name}`, `GET /projections`, `POST /model/reload` | `X-Service-Key` |
| `GET /health/live`, `GET /health/ready`, `GET /metrics` | none (cluster-internal) |

Input hardening: Pydantic v2 strict schema (exactly 28 finite features + amount, unknown fields rejected), batch size limit,
1 MiB body limit, validation errors never echo the input. The service refuses to start without `SERVICE_KEY`.
Decision rule: an uncertain prediction (uncertainty ≥ 0.25 or conformal set ≠ `{FRAUD}`) is **never** declined — it goes to `HUMAN_REVIEW`.

```powershell
cd mlops/serving
pip install -r requirements-dev.txt
pytest            # 25 tests, coverage gate 80 % (currently ~92 %)
docker build -f mlops/serving/Dockerfile -t ghcr.io/radahassan/riskpulse-ml-serving:dev .   # from the repo root
```

The model code and artifacts come from [`ml/`](../ml/) (`ml/src/ml/predictor.py`, `ml/artifacts/`).
