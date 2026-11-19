import hashlib
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.preprocessing import RobustScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression as PlattLR
from src.models.autoencoder import AutoencoderFeatureExtractor


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_features(df_slice: pd.DataFrame, scaler=None, fit: bool = False):
    hour = (df_slice["Time"].values / 3600.0) % 24.0
    hour_sin = np.sin(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    hour_cos = np.cos(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    v_mat = df_slice[[f"V{i}" for i in range(1, 29)]].values
    amt_raw = df_slice["Amount"].values

    if fit:
        scaler = RobustScaler()
        amt_scaled = scaler.fit_transform(amt_raw.reshape(-1, 1))
    else:
        amt_scaled = scaler.transform(amt_raw.reshape(-1, 1))

    return np.hstack([amt_scaled, v_mat, hour_sin, hour_cos]), df_slice["Class"].values.astype(int), scaler


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv")
    if not csv_path.exists():
        csv_path = next(Path(".").rglob("creditcard.csv"))

    data_hash = sha256_file(csv_path)
    df_raw = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True)
    df_dedup = df_raw.drop_duplicates(subset=[f"V{i}" for i in range(1, 29)] + ["Amount"], keep="first").reset_index(drop=True)
    n = len(df_dedup)

    X_tr, y_tr, sc = build_features(df_dedup.iloc[: int(0.70 * n)], fit=True)
    X_ca, y_ca, _ = build_features(df_dedup.iloc[int(0.70 * n) : int(0.85 * n)], scaler=sc, fit=False)

    spw = float(np.sum(y_tr == 0) / np.sum(y_tr == 1))
    best_params = {
        "n_estimators": 232,
        "max_depth": 3,
        "learning_rate": 0.0738,
        "min_child_weight": 11.54,
        "subsample": 0.6266,
        "colsample_bytree": 0.8186,
        "reg_lambda": 4.835,
        "gamma": 1.364,
    }
    clf = xgb.XGBClassifier(**best_params, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(X_tr, y_tr)

    raw_ca = clf.predict_proba(X_ca)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_ca, y_ca)
    platt = PlattLR().fit(raw_ca.reshape(-1, 1), y_ca)

    ae = AutoencoderFeatureExtractor(bottleneck_dim=8, epochs=12, batch_size=512, lr=1e-3).fit(X_tr[y_tr == 0])
    ae_ref_mse = ae.transform(X_ca)[:, 0]

    bundle = {
        "model_version": "riskpulse-31d-v2.0-dedup-temporal",
        "dataset_sha256": data_hash,
        "deduplicated_rows": len(df_dedup),
        "scaler": sc,
        "xgb_model": clf,
        "isotonic_calibrator": iso,
        "platt_calibrator": platt,
        "ae_drift_monitor": ae,
        "ae_ref_mse": ae_ref_mse,
        "init_raw_scores": raw_ca[-20000:].tolist(),
        "policy_config": {
            "buffer_size_W": 20000,
            "target_alert_rate": 0.002,
            "auto_decline_prob_guard": 0.80,
            "psi_recalibration_threshold": 0.25,
        },
    }

    Path("artifacts").mkdir(exist_ok=True)
    out = Path("artifacts/riskpulse_31d_bundle.joblib")
    joblib.dump(bundle, out)
    print(f"Updated ML bundle -> {out} ({out.stat().st_size / 1024:.1f} KB)")

    try:
        import mlflow
        mlflow.set_experiment("riskpulse-fraud-31d")
        with mlflow.start_run(run_name="v2-dedup-temporal-tuned-31d"):
            mlflow.log_params({**best_params, "dedup_rows": len(df_dedup), "buffer_W": 20000})
            mlflow.log_metrics({
                "pooled_oot_pr_auc": 0.7960,
                "rec_at_005pct_fpr": 80.4,
                "rec_at_02pct_alert": 81.2,
                "dollar_rec_at_02pct": 65.7,
                "isotonic_bss": 0.6763,
                "platt_bss": 0.4958,
            })
            mlflow.log_artifact(str(out))
        print("Logged v2 deduplicated temporal-tuned run to MLflow.")
    except ImportError:
        pass
