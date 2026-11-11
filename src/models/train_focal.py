import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef
from xgboost import XGBClassifier

from src.config import ARTIFACTS_DIR, XGB_PARAMS, RANDOM_STATE
from src.data_prep import load_and_split_data
from src.models.focal_loss import BinaryFocalLoss
from src.models.uncertainty import OperationalCalibrator
from src.stats.cost_optimization import compute_financial_loss

def run():
    print("[1/4] Loading modular dataset splits...")
    splits = load_and_split_data()
    X_train, y_train = splits["X_train"], splits["y_train"]
    X_cal, y_cal = splits["X_cal"], splits["y_cal"]
    X_test, y_test = splits["X_test"], splits["y_test"]

    print("[2/4] Initializing Asymmetric Focal Loss (gamma=2.0, alpha=0.75)...")
    focal = BinaryFocalLoss(gamma=2.0, alpha=0.75)

    params = XGB_PARAMS.copy()
    # Replace default binary:logistic with custom objective
    params["objective"] = focal.objective
    params["disable_default_eval_metric"] = 1
    # Remove logloss from parameters when using custom objective
    if "eval_metric" in params:
        del params["eval_metric"]

    print("[3/4] Fitting XGBoost with Asymmetric Focal Loss objective...")
    focal_xgb = XGBClassifier(**params)
    focal_xgb.fit(X_train, y_train)

    # Monotonic Isotonic Calibration
    # Note: For custom objectives, predict_proba returns calibrated probabilities from margins
    raw_cal = focal_xgb.predict(X_cal, output_margin=True)
    probs_cal_raw = 1.0 / (1.0 + np.exp(-raw_cal))
    calibrator = OperationalCalibrator().fit(probs_cal_raw, y_cal)

    raw_test = focal_xgb.predict(X_test, output_margin=True)
    probs_test_raw = 1.0 / (1.0 + np.exp(-raw_test))
    cal_test_p = calibrator.predict_proba(probs_test_raw)

    print("[4/4] Evaluating Focal Loss model on holdout test set...")
    pr_auc = average_precision_score(y_test, cal_test_p)
    f1 = f1_score(y_test, (cal_test_p >= 0.1442).astype(int))
    mcc = matthews_corrcoef(y_test, (cal_test_p >= 0.1442).astype(int))

    # Retrieve test amounts for financial evaluation
    df_raw = pd.read_csv("data/creditcard.csv")
    from sklearn.model_selection import train_test_split
    from src.config import TEST_SIZE
    _, idx_test = train_test_split(np.arange(len(df_raw)), test_size=TEST_SIZE, stratify=df_raw["Class"], random_state=RANDOM_STATE)
    amounts_test = df_raw["Amount"].iloc[idx_test].values

    loss, fp, fn, tp = compute_financial_loss(y_test, cal_test_p, amounts_test, threshold=0.1442)

    print("\n--- Focal Loss Model Benchmark (Test Set at t* = 0.1442) ---")
    print(f"  PR-AUC (Average Precision): {pr_auc:.4f}")
    print(f"  F1-Score:                   {f1:.4f}")
    print(f"  Matthews Corr Coef (MCC):   {mcc:.4f}")
    print(f"  Financial Dollar Loss:      ${loss:,.2f}")
    print(f"  Confusion Breakdown:        TP={tp}/74 | FN={fn} | FP={fp}")

    joblib.dump(focal_xgb, ARTIFACTS_DIR / "focal_xgb.joblib")
    joblib.dump(calibrator.calibrator, ARTIFACTS_DIR / "focal_iso_calibrator.joblib")
    print(f"\nArtifacts saved to {ARTIFACTS_DIR}/focal_xgb.joblib")

if __name__ == "__main__":
    run()
