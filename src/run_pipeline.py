import json
import joblib
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.calibration import calibration_curve
from sklearn.metrics import confusion_matrix
from xgboost import XGBClassifier

from src.config import ARTIFACTS_DIR, FIGS_DIR, XGB_PARAMS, REVIEW_LOWER_BOUND, REVIEW_UPPER_BOUND
from src.data_prep import load_and_split_data
from src.metrics_utils import evaluate_predictions
from src.models.uncertainty import OperationalCalibrator

def run():
    print("[1/4] Loading modular data splits...")
    splits = load_and_split_data()
    
    # Save the splits so validation and visualization scripts can load them
    np.savez_compressed(
        ARTIFACTS_DIR / "data_splits.npz",
        X_test=splits["X_test"],
        y_test=splits["y_test"]
    )
    
    scale_pos_weight = float((splits["y_train"] == 0).sum() / (splits["y_train"] == 1).sum())
    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = scale_pos_weight
    
    print("[2/4] Training Champion XGBoost with Tuned Hyperparameters...")
    model = XGBClassifier(**params)
    model.fit(splits["X_train"], splits["y_train"])
    
    print("[3/4] Fitting Isotonic Probability Calibrator...")
    raw_cal = model.predict_proba(splits["X_cal"])[:, 1]
    calibrator = OperationalCalibrator().fit(raw_cal, splits["y_cal"])
    
    print("[4/4] Evaluating on holdout test set...")
    raw_test = model.predict_proba(splits["X_test"])[:, 1]
    cal_test_p = calibrator.predict_proba(raw_test)
    
    clf_metrics = evaluate_predictions(splits["y_test"], cal_test_p)
    preds, is_rev, unc_metrics = calibrator.route_transactions(cal_test_p, splits["y_test"])
    
    print(f"      ECE: {clf_metrics['ece']:.4f} | Brier: {clf_metrics['brier_score']:.5f}")
    print(f"      Review Rate: {unc_metrics['human_review_rate_pct']:.2f}% ({unc_metrics['total_reviews']} txns)")
    print(f"      Frauds Caught: {unc_metrics['frauds_intercepted']}/{unc_metrics['total_frauds']}")
    
    # Diagnostic Curves
    prob_true, prob_pred = calibration_curve(splits["y_test"], cal_test_p, n_bins=10)
    plt.figure(figsize=(6, 5))
    plt.plot(prob_pred, prob_true, marker='o', label='Calibrated XGBoost')
    plt.plot([0, 1], [0, 1], linestyle='--', label='Perfect Calibration')
    plt.title(f"Reliability Diagram (ECE = {clf_metrics['ece']:.4f})")
    plt.xlabel("Mean Predicted Probability")
    plt.ylabel("Observed Fraction of Positives")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGS_DIR / "reliability_diagram.png")
    plt.close()
    
    cm = confusion_matrix(splits["y_test"], preds)
    plt.figure(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False)
    plt.title("Confusion Matrix (Test Split)")
    plt.xlabel("Predicted Class")
    plt.ylabel("True Class")
    plt.tight_layout()
    plt.savefig(FIGS_DIR / "confusion_matrix.png")
    plt.close()
    
    # Save standard component artifacts for the MLOps engineer
    joblib.dump(splits["preprocessor"], ARTIFACTS_DIR / "preprocessor.joblib")
    joblib.dump(model, ARTIFACTS_DIR / "base_xgb.joblib")
    joblib.dump(calibrator.calibrator, ARTIFACTS_DIR / "iso_calibrator.joblib")
    
    meta = {
        "review_lower_bound": REVIEW_LOWER_BOUND,
        "review_upper_bound": REVIEW_UPPER_BOUND,
        "metrics": {**clf_metrics, **unc_metrics}
    }
    with open(ARTIFACTS_DIR / "conformal.json", "w") as f:
        json.dump(meta, f, indent=2)
        
    print("\nData Science artifacts exported cleanly to artifacts/ for MLOps handoff.")

if __name__ == "__main__":
    run()
