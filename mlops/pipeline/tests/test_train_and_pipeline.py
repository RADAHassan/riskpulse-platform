import numpy as np
import pandas as pd
import pytest
from common import Context
from train import train_bundle


def synthetic_ulb(path, n=4000, frauds=60, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, 28)), columns=[f"V{i}" for i in range(1, 29)])
    y = np.zeros(n, int)
    y[rng.choice(n, frauds, replace=False)] = 1
    df.loc[y == 1, ["V1", "V3", "V14"]] -= 4.0
    df.insert(0, "Time", np.arange(n, dtype=float))
    df["Amount"] = rng.lognormal(3.5, 1.0, n).round(2)
    df["Class"] = y
    df.to_csv(path, index=False)
    return path


def test_train_bundle_produces_a_loadable_bundle(tmp_path):
    csv = synthetic_ulb(tmp_path / "creditcard.csv")
    out, metrics = train_bundle(csv, tmp_path / "bundle.joblib", ae_epochs=1)
    assert out.exists()
    assert metrics["n_holdout"] > 0

    from src.ml.predictor import RiskPulseMLPredictor

    p = RiskPulseMLPredictor(bundle_path=str(out))
    res = p.score_transaction(50.0, [0.0] * 28)
    assert res["decision"] in {"APPROVE", "MANUAL_REVIEW", "AUTO_DECLINE"}
    assert res["model_version"] == "riskpulse-29d-retrained"


def test_import_mode_pipeline_registers_a_champion(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    import common
    import run_pipeline

    monkeypatch.setattr(common, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.chdir(tmp_path)
    code = run_pipeline.main(["--mode", "import", "--stages", "train", "evaluate", "validate", "register", "deploy"])
    assert code == 0

    client = mlflow.MlflowClient()
    mv = client.get_model_version_by_alias("riskpulse-fraud", "champion")
    assert mv.tags["gates_passed"] == "True"
    assert mv.tags["gate.G1_xgboost_not_significantly_inferior"] == "True"
    state = Context.load()
    assert state.alias == "champion"
    assert state.deployed is False  # SERVING_URL not set: deployment is recorded as skipped
