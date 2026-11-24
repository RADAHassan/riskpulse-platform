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


def build_29d(df_slice: pd.DataFrame, scaler=None, fit: bool = False):
    v_mat = df_slice[[f"V{i}" for i in range(1, 29)]].values
    amt_raw = df_slice["Amount"].values
    if fit:
        scaler = RobustScaler()
        amt_scaled = scaler.fit_transform(amt_raw.reshape(-1, 1))
    else:
        amt_scaled = scaler.transform(amt_raw.reshape(-1, 1))
    return np.hstack([amt_scaled, v_mat]), df_slice["Class"].values.astype(int), scaler


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv") if Path("data/creditcard.csv").exists() else next(Path(".").rglob("creditcard.csv"))
    data_hash = sha256_file(csv_path)
    df = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True).drop_duplicates(keep="first").reset_index(drop=True)
    n = len(df)

    X_tr, y_tr, sc = build_29d(df.iloc[: int(0.70 * n)], fit=True)
    X_ca, y_ca, _ = build_29d(df.iloc[int(0.70 * n) : int(0.85 * n)], scaler=sc, fit=False)

    spw = float(np.sum(y_tr == 0) / np.sum(y_tr == 1))
    params_29 = {
        "n_estimators": 220,
        "max_depth": 3,
        "learning_rate": 0.1023,
        "min_child_weight": 11.23,
        "subsample": 0.9949,
        "colsample_bytree": 0.8689,
        "reg_lambda": 0.7019,
        "gamma": 1.7418,
    }
    clf = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(X_tr, y_tr)
    raw_ca = clf.predict_proba(X_ca)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_ca, y_ca)
    platt = PlattLR().fit(raw_ca.reshape(-1, 1), y_ca)

    ae = AutoencoderFeatureExtractor(bottleneck_dim=8, epochs=12, batch_size=512, lr=1e-3).fit(X_tr[y_tr == 0])
    ae_ref_mse = ae.transform(X_ca)[:, 0]

    bundle = {
        "model_version": "riskpulse-29d-v2.0-canonical",
        "dataset_sha256": data_hash,
        "deduplicated_rows": len(df),
        "feature_schema": ["Amount_RobustScaled"] + [f"V{i}" for i in range(1, 29)],
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
    out = Path("artifacts/riskpulse_29d_bundle.joblib")
    joblib.dump(bundle, out)
    print(f"Exported canonical 29D bundle -> {out} ({out.stat().st_size / 1024:.1f} KB)")
