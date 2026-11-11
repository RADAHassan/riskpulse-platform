import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef
from xgboost import XGBClassifier

from src.config import ARTIFACTS_DIR, XGB_PARAMS, RANDOM_STATE
from src.data_prep import load_and_split_data
from src.models.autoencoder import AutoencoderFeatureExtractor
from src.models.uncertainty import OperationalCalibrator

def run():
    print("[1/4] Loading modular dataset splits...")
    splits = load_and_split_data()
    X_train, y_train = splits["X_train"], splits["y_train"]
    X_cal, y_cal = splits["X_cal"], splits["y_cal"]
    X_test, y_test = splits["X_test"], splits["y_test"]

    print("[2/4] Training Semi-Supervised Autoencoder strictly on clean samples (Y=0)...")
    legit_mask = (y_train == 0)
    X_train_legit = X_train[legit_mask]

    ae = AutoencoderFeatureExtractor(bottleneck_dim=8, epochs=12, batch_size=512, lr=1e-3)
    ae.fit(X_train_legit)
    ae.save(ARTIFACTS_DIR / "autoencoder.joblib")

    print("[3/4] Extracting reconstruction error and latent embeddings...")
    ae_train = ae.transform(X_train)
    ae_cal = ae.transform(X_cal)
    ae_test = ae.transform(X_test)

    # Concatenate original features + Autoencoder anomaly features
    X_train_aug = np.hstack([X_train, ae_train])
    X_cal_aug = np.hstack([X_cal, ae_cal])
    X_test_aug = np.hstack([X_test, ae_test])

    print(f"      Feature space expanded from {X_train.shape[1]} to {X_train_aug.shape[1]} features.")

    print("[4/4] Fitting Calibrated Tuned XGBoost on Hybrid Representation...")
    scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())
    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = scale_pos_weight

    hybrid_xgb = XGBClassifier(**params)
    hybrid_xgb.fit(X_train_aug, y_train)

    # Monotonic Isotonic Calibration
    raw_cal = hybrid_xgb.predict_proba(X_cal_aug)[:, 1]
    calibrator = OperationalCalibrator().fit(raw_cal, y_cal)

    # Evaluate on Test Split
    raw_test = hybrid_xgb.predict_proba(X_test_aug)[:, 1]
    cal_test_p = calibrator.predict_proba(raw_test)

    pr_auc_hybrid = average_precision_score(y_test, cal_test_p)
    f1_hybrid = f1_score(y_test, (cal_test_p >= 0.1442).astype(int))
    mcc_hybrid = matthews_corrcoef(y_test, (cal_test_p >= 0.1442).astype(int))

    print("\n--- Hybrid Model Benchmark (Test Set at t* = 0.1442) ---")
    print(f"  PR-AUC (Average Precision): {pr_auc_hybrid:.4f}")
    print(f"  F1-Score:                   {f1_hybrid:.4f}")
    print(f"  Matthews Corr Coef (MCC):   {mcc_hybrid:.4f}")

    joblib.dump(hybrid_xgb, ARTIFACTS_DIR / "hybrid_xgb.joblib")
    joblib.dump(calibrator.calibrator, ARTIFACTS_DIR / "hybrid_iso_calibrator.joblib")
    print(f"\nArtifacts saved to {ARTIFACTS_DIR}/hybrid_xgb.joblib")

if __name__ == "__main__":
    run()
