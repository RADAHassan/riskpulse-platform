"""Stage 1 — Training.

* ``train`` mode (ULB dataset present): re-trains the canonical 29D bundle with the same recipe and
  hyper-parameters as ``ml/src/ml/export_29d_canonical.py`` (chronological split: train [0, 70 %],
  isotonic calibration [70 %, 85 %], hold-out [85 %, 100 %]).
* ``import`` mode (dataset absent): nothing is retrained. The shipped bundle and its parameters are logged
  so the registry entry is traceable to the exact artifact.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import mlflow
import numpy as np
from common import ARTIFACTS, DATASET, Context, flat, start_stage

XGB_PARAMS = {
    "n_estimators": 220,
    "max_depth": 3,
    "learning_rate": 0.1023,
    "min_child_weight": 11.23,
    "subsample": 0.9949,
    "colsample_bytree": 0.8689,
    "reg_lambda": 0.7019,
    "gamma": 1.7418,
}
POLICY = {
    "buffer_size_W": 20000,
    "target_alert_rate": 0.002,
    "auto_decline_prob_guard": 0.80,
    "psi_recalibration_threshold": 0.25,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def train_bundle(csv_path: Path, out_path: Path, ae_epochs: int = 12) -> tuple[Path, dict]:
    """Train the canonical bundle from a ULB-format CSV. Returns (bundle path, hold-out metrics)."""
    import pandas as pd
    import xgboost as xgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    from sklearn.preprocessing import RobustScaler
    from src.models.autoencoder import AutoencoderFeatureExtractor

    df = (pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True)
          .drop_duplicates(keep="first").reset_index(drop=True))
    n = len(df)
    vcols = [f"V{i}" for i in range(1, 29)]

    def matrix(part, scaler=None):
        amt = part["Amount"].to_numpy().reshape(-1, 1)
        scaler = scaler or RobustScaler().fit(amt)
        return np.hstack([scaler.transform(amt), part[vcols].to_numpy()]), part["Class"].to_numpy().astype(int), scaler

    x_tr, y_tr, scaler = matrix(df.iloc[: int(0.70 * n)])
    x_ca, y_ca, _ = matrix(df.iloc[int(0.70 * n): int(0.85 * n)], scaler)
    x_ho, y_ho, _ = matrix(df.iloc[int(0.85 * n):], scaler)

    spw = float(np.sum(y_tr == 0) / max(np.sum(y_tr == 1), 1))
    clf = xgb.XGBClassifier(**XGB_PARAMS, scale_pos_weight=spw, eval_metric="logloss",
                            random_state=42, n_jobs=-1).fit(x_tr, y_tr)
    raw_ca = clf.predict_proba(x_ca)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_ca, y_ca)
    ae = AutoencoderFeatureExtractor(bottleneck_dim=8, epochs=ae_epochs, batch_size=512, lr=1e-3).fit(x_tr[y_tr == 0])

    bundle = {
        "model_version": "riskpulse-29d-retrained",
        "dataset_sha256": sha256_file(csv_path),
        "deduplicated_rows": n,
        "feature_schema": ["Amount_RobustScaled", *vcols],
        "scaler": scaler,
        "xgb_model": clf,
        "isotonic_calibrator": iso,
        "ae_drift_monitor": ae,
        "ae_ref_mse": ae.transform(x_ca)[:, 0],
        "init_raw_scores": raw_ca[-POLICY["buffer_size_W"]:].tolist(),
        "policy_config": dict(POLICY),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out_path)

    raw_ho = clf.predict_proba(x_ho)[:, 1]
    cal_ho = iso.predict(raw_ho)
    metrics = {"n_holdout": float(len(y_ho)), "n_holdout_frauds": float(y_ho.sum())}
    if 0 < y_ho.sum() < len(y_ho):
        metrics.update({
            "pr_auc": float(average_precision_score(y_ho, cal_ho)),
            "roc_auc": float(roc_auc_score(y_ho, raw_ho)),
            "brier_calibrated": float(brier_score_loss(y_ho, cal_ho)),
            "brier_raw": float(brier_score_loss(y_ho, raw_ho)),
        })
    return out_path, metrics


def run(ctx: Context) -> Context:
    with start_stage("training", ctx):
        mlflow.log_param("mode", ctx.mode)
        mlflow.log_params({f"xgb_{k}": v for k, v in XGB_PARAMS.items()})
        mlflow.log_params({f"policy_{k}": v for k, v in POLICY.items()})
        if ctx.mode == "train":
            mlflow.log_param("dataset_sha256", sha256_file(DATASET))
            bundle, holdout = train_bundle(DATASET, Path(ctx.out_dir) / "riskpulse_29d_bundle.joblib")
            ctx.bundle_path = str(bundle)
            ctx.metrics["train"] = holdout
            mlflow.log_metrics(flat("train_holdout_", holdout))
        else:
            from src.ml.bundle_io import load_bundle

            shipped = load_bundle(ctx.bundle_path)
            mlflow.log_param("import_reason", "dataset absent: logging the shipped bundle without retraining")
            mlflow.log_param("bundle_model_version", shipped["model_version"])
            mlflow.log_param("bundle_dataset_sha256", shipped.get("dataset_sha256", "n/a"))
            mlflow.log_param("bundle_dedup_rows", shipped.get("deduplicated_rows", "n/a"))
        mlflow.log_param("bundle_sha256", sha256_file(Path(ctx.bundle_path)))
        mlflow.log_artifact(ctx.bundle_path, "bundle")
        mlflow.log_artifact(str(ARTIFACTS / "conformal.json"), "bundle")
    return ctx


if __name__ == "__main__":
    c = Context.load()
    run(c)
    c.save()
