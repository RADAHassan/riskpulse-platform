import numpy as np
import joblib

def run_sweep():
    print("[Sweep] Loading calibrated artifacts and test data...")
    data = np.load("artifacts/data_splits.npz")
    X_test = data["X_test"]
    y_test = data["y_test"]

    base_xgb = joblib.load("artifacts/base_xgb.joblib")
    calibrator = joblib.load("artifacts/iso_calibrator.joblib")

    raw_test_p1 = base_xgb.predict_proba(X_test)[:, 1]
    cal_test_p1 = calibrator.predict(raw_test_p1)
    preds = (cal_test_p1 >= 0.5).astype(int)

    lower_thresholds = [0.005, 0.010, 0.020, 0.050]
    upper_thresholds = [0.60, 0.70, 0.80]
    total_txns = len(y_test)
    total_frauds = int(np.sum(y_test == 1))

    print("\n--- Operational Routing Parameter Sweep (Test Set) ---")
    print(f"{'Band [Low, High]':<20} | {'Review Rate':<12} | {'Fraud Coverage':<15} | {'Intercepted':<12}")
    print("-" * 65)

    for low in lower_thresholds:
        for high in upper_thresholds:
            is_review = (cal_test_p1 >= low) & (cal_test_p1 <= high)
            in_set_1 = cal_test_p1 >= low
            fraud_cov = np.mean(in_set_1[y_test == 1]) * 100.0
            rev_rate = np.mean(is_review) * 100.0
            intercepted = int(np.sum(is_review[y_test == 1] | (preds[y_test == 1] == 1)))

            band_str = f"[{low:.3f}, {high:.2f}]"
            rev_str = f"{rev_rate:.2f}% ({int(np.sum(is_review))})"
            cov_str = f"{fraud_cov:.2f}%"
            caught_str = f"{intercepted}/{total_frauds}"
            print(f"{band_str:<20} | {rev_str:<12} | {cov_str:<15} | {caught_str:<12}")
    print("-" * 65)

if __name__ == "__main__":
    run_sweep()
