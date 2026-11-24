"""Shared helpers for the RiskPulse MLOps pipeline.

Stages: train -> evaluate -> validate_stats -> register -> deploy (orchestrated by run_pipeline.py).
Each stage is a nested MLflow run under one parent pipeline run, and can also be launched on its own
(``python mlops/pipeline/evaluate.py``) thanks to the small state file written next to the scripts.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ML_DIR = REPO / "ml"
ARTIFACTS = ML_DIR / "artifacts"
STATE_FILE = HERE / ".pipeline_state.json"
DATASET = ML_DIR / "data" / "creditcard.csv"

EXPERIMENT = "riskpulse-fraud"
REGISTERED_MODEL = "riskpulse-fraud"
CHAMPION_ALIAS = "champion"
CHALLENGER_ALIAS = "challenger"

# the pickled bundle references `src.models.autoencoder`
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def tracking_uri() -> str:
    """MLflow tracking server (env MLFLOW_TRACKING_URI) or a local SQLite file for offline runs."""
    return os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{(HERE / 'mlflow-local.db').as_posix()}"


def dataset_present() -> bool:
    return DATASET.exists()


@dataclass
class Context:
    mode: str = "auto"  # "train" | "import" (resolved by resolve_mode)
    parent_run_id: str | None = None
    experiment_id: str | None = None
    bundle_path: str = str(ARTIFACTS / "riskpulse_29d_bundle.joblib")
    conformal_path: str = str(ARTIFACTS / "conformal.json")
    out_dir: str = str(HERE / "out")
    metrics: dict = field(default_factory=dict)
    gates: dict = field(default_factory=dict)
    gates_passed: bool | None = None
    model_version: str | None = None
    alias: str | None = None
    deployed: bool = False

    def save(self) -> None:
        STATE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> Context:
        if STATE_FILE.exists():
            return cls(**json.loads(STATE_FILE.read_text(encoding="utf-8")))
        return cls()


def resolve_mode(requested: str) -> str:
    if requested == "auto":
        return "train" if dataset_present() else "import"
    if requested == "train" and not dataset_present():
        raise SystemExit(f"--mode train needs the ULB dataset at {DATASET}; use --mode import")
    return requested


def start_stage(name: str, ctx: Context):
    """Open a nested MLflow run for a stage under the parent pipeline run."""
    import mlflow

    mlflow.set_tracking_uri(tracking_uri())
    return mlflow.start_run(run_name=name, nested=True, parent_run_id=ctx.parent_run_id,
                            experiment_id=ctx.experiment_id, tags={"stage": name})


def log_json_artifact(obj: dict | list, name: str, ctx: Context) -> Path:
    import mlflow

    out = Path(ctx.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    mlflow.log_artifact(str(path))
    return path


def flat(prefix: str, d: dict) -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}".replace("@", "_at_").replace("%", "pct").replace(" ", "_")
        key = key.replace("(", "").replace(")", "")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = float(v)
    return out
