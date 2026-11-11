import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef
from sklearn.preprocessing import RobustScaler
from sklearn.compose import ColumnTransformer
from xgboost import XGBClassifier

from src.config import DATA_PATH, ARTIFACTS_DIR, XGB_PARAMS
from src.models.uncertainty import OperationalCalibrator
from src.stats.cost_optimization import compute_financial_loss

def run():
    print("[1/4] Loading dataset and performing Chronological Out-Of-Time (OOT) Split...")
    df = pd.read_csv(DATA_PATH)
    
    # Sort strictly by time to preserve sequential reality
    df = df.sort_values("Time").reset_index(drop=True)
    
    # Cyclical hour encoding
    hour = (df["Time"] / 3600.0) % 24
    df["Hour_Sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["Hour_Cos"] = np.cos(2 * np.pi * hour / 24.0)
    
    n_total = len(df)
    n_train = int(n_total * 0.70)
    n_cal = int(n_total * 0.85)
    
    train_df = df.iloc[:n_train]
    cal_df = df.iloc[n_train:n_cal]
    test_df = df.iloc[n_cal:]
    
    print(f"      Train window:       0.0h -> {train_df['Time'].max()/3600:.1f}h ({len(train_df):,} txns, {train_df['Class'].sum()} frauds)")
    print(f"      Calibration window: {train_df['Time'].max()/3600:.1f}h -> {cal_df['Time'].max()/3600:.1f}h ({len(cal_df):,} txns, {cal_df['Class'].sum()} frauds)")
    print(f"      Out-Of-Time Test:   {cal_df['Time'].max()/3600:.1f}h -> {test_df['Time'].max()/3600:.1f}h ({len(test_df):,} txns, {test_df['Class'].sum()} frauds)")

    feature_cols = [c for c in df.columns if c not in ["Time", "Class"]]
    
    preprocessor = ColumnTransformer(
        transformers=[
            ("scaler", RobustScaler(), ["Amount"]),
            ("pass", "passthrough", [c for c in feature_cols if c != "Amount"])
        ]
    )
    
    X_train = preprocessor.fit_transform(train_df[feature_cols])
    y_train = train_df["Class"].values
    
    X_cal = preprocessor.transform(cal_df[feature_cols])
    y_cal = cal_df["Class"].values
    
    X_test = preprocessor.transform(test_df[feature_cols])
    y_test = test_df["Class"].values
    
    print("[2/4] Training Tuned XGBoost on chronological Train split...")
    scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())
    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = scale_pos_weight
    
    model = XGBClassifier(**params)
    model.fit(X_train, y_train)
    
    print("[3/4] Calibrating probabilities on temporal Calibration split...")
    raw_cal = model.predict_proba(X_cal)[:, 1]
    calibrator = OperationalCalibrator().fit(raw_cal, y_cal)
    
    # Search for optimal threshold t* strictly on chronological calibration window
    cal_probs = calibrator.predict_proba(raw_cal)
    threshold_grid = np.linspace(0.01, 0.90, 180)
    amounts_cal = cal_df["Amount"].values
    
    best_t = 0.50
    min_loss = float("inf")
    for t in threshold_grid:
        loss, _, _, _ = compute_financial_loss(y_cal, cal_probs, amounts_cal, threshold=t)
        if loss < min_loss:
            min_loss = loss
            best_t = t
            
    print(f"      Empirical OOT Optimal Threshold (t*): {best_t:.4f}")
    
    print("[4/4] Evaluating on Unseen Future Out-Of-Time Test Split...")
    raw_test = model.predict_proba(X_test)[:, 1]
    cal_test_p = calibrator.predict_proba(raw_test)
    
    pr_auc_oot = average_precision_score(y_test, cal_test_p)
    preds_oot = (cal_test_p >= best_t).astype(int)
    f1_oot = f1_score(y_test, preds_oot)
    mcc_oot = matthews_corrcoef(y_test, preds_oot)
    
    amounts_test = test_df["Amount"].values
    loss_oot, fp, fn, tp = compute_financial_loss(y_test, cal_test_p, amounts_test, threshold=best_t)
    loss_default, fp_def, fn_def, tp_def = compute_financial_loss(y_test, cal_test_p, amounts_test, threshold=0.50)
    
    print(f"\n--- Chronological Out-Of-Time (OOT) Benchmark ---")
    print(f"  OOT PR-AUC (Average Precision): {pr_auc_oot:.4f}")
    print(f"  OOT F1-Score (at t*={best_t:.4f}):   {f1_oot:.4f}")
    print(f"  OOT MCC:                        {mcc_oot:.4f}")
    print(f"  Default (0.50) Loss:            ${loss_default:,.2f} (TP={tp_def}/{y_test.sum()}, FN={fn_def}, FP={fp_def})")
    print(f"  OOT Optimized (t*) Loss:        ${loss_oot:,.2f} (TP={tp}/{y_test.sum()}, FN={fn}, FP={fp})")
    print(f"  Net Future Savings:             ${loss_default - loss_oot:,.2f}")
    
    joblib.dump(model, ARTIFACTS_DIR / "oot_xgb.joblib")

if __name__ == "__main__":
    run()
