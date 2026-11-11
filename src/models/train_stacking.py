import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

from src.config import ARTIFACTS_DIR, RANDOM_STATE, XGB_PARAMS
from src.data_prep import load_and_split_data
from src.models.uncertainty import OperationalCalibrator
from src.stats.cost_optimization import compute_financial_loss

def run():
    print("[1/4] Loading modular dataset splits...")
    splits = load_and_split_data()
    X_train, y_train = splits["X_train"], splits["y_train"]
    X_cal, y_cal = splits["X_cal"], splits["y_cal"]
    X_test, y_test = splits["X_test"], splits["y_test"]

    scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())

    print("[2/4] Training Heterogeneous Base Learners...")
    # Model 1: Tuned XGBoost
    print("      -> [1/3] Training XGBoost...")
    params_xgb = XGB_PARAMS.copy()
    params_xgb["scale_pos_weight"] = scale_pos_weight
    model_xgb = XGBClassifier(**params_xgb)
    model_xgb.fit(X_train, y_train)

    # Model 2: LightGBM (Leaf-wise splits)
    print("      -> [2/3] Training LightGBM...")
    model_lgb = LGBMClassifier(
        n_estimators=180,
        learning_rate=0.08,
        num_leaves=31,
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1
    )
    model_lgb.fit(X_train, y_train)

    # Model 3: CatBoost (Symmetric trees)
    print("      -> [3/3] Training CatBoost...")
    model_cat = CatBoostClassifier(
        iterations=200,
        learning_rate=0.08,
        depth=5,
        scale_pos_weight=scale_pos_weight,
        random_seed=RANDOM_STATE,
        verbose=0
    )
    model_cat.fit(X_train, y_train)

    print("[3/4] Blending Base Learners via Logistic Meta-Learner on Calibration split...")
    # Extract prediction probabilities on calibration split
    p_xgb_cal = model_xgb.predict_proba(X_cal)[:, 1]
    p_lgb_cal = model_lgb.predict_proba(X_cal)[:, 1]
    p_cat_cal = model_cat.predict_proba(X_cal)[:, 1]
    
    meta_features_cal = np.column_stack([p_xgb_cal, p_lgb_cal, p_cat_cal])

    meta_learner = LogisticRegression(C=1.0, penalty="l2", random_state=RANDOM_STATE)
    meta_learner.fit(meta_features_cal, y_cal)
    
    # Calibrate blended probabilities
    blended_cal_raw = meta_learner.predict_proba(meta_features_cal)[:, 1]
    calibrator = OperationalCalibrator().fit(blended_cal_raw, y_cal)

    print("[4/4] Evaluating Stacking Ensemble on Holdout Test Split...")
    p_xgb_test = model_xgb.predict_proba(X_test)[:, 1]
    p_lgb_test = model_lgb.predict_proba(X_test)[:, 1]
    p_cat_test = model_cat.predict_proba(X_test)[:, 1]
    
    meta_features_test = np.column_stack([p_xgb_test, p_lgb_test, p_cat_test])
    blended_test_raw = meta_learner.predict_proba(meta_features_test)[:, 1]
    cal_test_p = calibrator.predict_proba(blended_test_raw)

    # Evaluate Metrics
    pr_auc = average_precision_score(y_test, cal_test_p)
    preds = (cal_test_p >= 0.1442).astype(int)
    f1 = f1_score(y_test, preds)
    mcc = matthews_corrcoef(y_test, preds)

    # Financial loss comparison
    df_raw = pd.read_csv("data/creditcard.csv")
    from sklearn.model_selection import train_test_split
    from src.config import TEST_SIZE
    _, idx_test = train_test_split(np.arange(len(df_raw)), test_size=TEST_SIZE, stratify=df_raw["Class"], random_state=RANDOM_STATE)
    amounts_test = df_raw["Amount"].iloc[idx_test].values

    loss, fp, fn, tp = compute_financial_loss(y_test, cal_test_p, amounts_test, threshold=0.1442)

    print("\n--- Multi-Architecture Stacking Benchmark (Test Set at t* = 0.1442) ---")
    print(f"  PR-AUC (Average Precision): {pr_auc:.4f}")
    print(f"  F1-Score:                   {f1:.4f}")
    print(f"  Matthews Corr Coef (MCC):   {mcc:.4f}")
    print(f"  Financial Dollar Loss:      ${loss:,.2f}")
    print(f"  Confusion Breakdown:        TP={tp}/74 | FN={fn} | FP={fp}")
    print(f"  Meta-Learner Weights:       XGB={meta_learner.coef_[0][0]:.3f}, LGB={meta_learner.coef_[0][1]:.3f}, CAT={meta_learner.coef_[0][2]:.3f}")

    joblib.dump(
        {"xgb": model_xgb, "lgb": model_lgb, "cat": model_cat, "meta": meta_learner, "calibrator": calibrator.calibrator},
        ARTIFACTS_DIR / "stacking_ensemble.joblib"
    )
    print(f"Ensemble artifacts successfully saved to {ARTIFACTS_DIR / 'stacking_ensemble.joblib'}")

if __name__ == "__main__":
    run()
