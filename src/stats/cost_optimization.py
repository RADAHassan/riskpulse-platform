import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.config import ARTIFACTS_DIR, FIGS_DIR

def compute_financial_loss(y_true, y_prob, amounts, threshold, c_fp=10.0, c_chargeback=25.0, c_investigate=2.0):
    preds = (y_prob >= threshold).astype(int)
    
    # Masks
    fp_mask = (y_true == 0) & (preds == 1)
    fn_mask = (y_true == 1) & (preds == 0)
    tp_mask = (y_true == 1) & (preds == 1)
    
    # Financial costs
    cost_fp = np.sum(fp_mask) * c_fp
    cost_fn = np.sum(amounts[fn_mask] + c_chargeback)
    cost_tp = np.sum(tp_mask) * c_investigate
    
    total_loss = float(cost_fp + cost_fn + cost_tp)
    return total_loss, int(np.sum(fp_mask)), int(np.sum(fn_mask)), int(np.sum(tp_mask))

def run():
    print("[1/3] Loading calibrated artifacts and raw amounts...")
    splits = np.load(ARTIFACTS_DIR / "data_splits.npz")
    X_test, y_test = splits["X_test"], splits["y_test"]
    
    # Load unscaled raw data to retrieve true dollar Amounts
    df_raw = pd.read_csv("data/creditcard.csv")
    amounts_all = df_raw["Amount"].values
    
    # Align amounts to splits using reproducible index logic
    from sklearn.model_selection import train_test_split
    from src.config import TEST_SIZE, CAL_SIZE, RANDOM_STATE
    
    indices = np.arange(len(df_raw))
    idx_tr_val, idx_test = train_test_split(indices, test_size=TEST_SIZE, stratify=df_raw["Class"], random_state=RANDOM_STATE)
    idx_train, idx_cal = train_test_split(idx_tr_val, test_size=CAL_SIZE, stratify=df_raw["Class"].iloc[idx_tr_val], random_state=RANDOM_STATE)
    
    amounts_cal = amounts_all[idx_cal]
    amounts_test = amounts_all[idx_test]
    y_cal = df_raw["Class"].iloc[idx_cal].values
    
    # Generate calibrated probabilities
    base_xgb = joblib.load(ARTIFACTS_DIR / "base_xgb.joblib")
    calibrator = joblib.load(ARTIFACTS_DIR / "iso_calibrator.joblib")
    
    # Calibration set predictions
    from src.data_prep import load_and_split_data
    split_dict = load_and_split_data()
    raw_cal = base_xgb.predict_proba(split_dict["X_cal"])[:, 1]
    probs_cal = calibrator.predict(raw_cal)
    
    # Test set predictions
    raw_test = base_xgb.predict_proba(X_test)[:, 1]
    probs_test = calibrator.predict(raw_test)

    print("[2/3] Searching for optimal cost-minimizing threshold on Calibration split...")
    threshold_grid = np.linspace(0.01, 0.90, 180)
    cal_losses = []
    
    for t in threshold_grid:
        loss, _, _, _ = compute_financial_loss(y_cal, probs_cal, amounts_cal, threshold=t)
        cal_losses.append(loss)
        
    best_idx = int(np.argmin(cal_losses))
    optimal_threshold = float(threshold_grid[best_idx])
    min_cal_loss = cal_losses[best_idx]
    
    print(f"      Optimal Financial Threshold (t*): {optimal_threshold:.4f}")
    
    print("[3/3] Evaluating Financial Savings on Holdout Test Split...")
    # Baseline comparison at default threshold 0.50
    loss_default, fp_def, fn_def, tp_def = compute_financial_loss(y_test, probs_test, amounts_test, threshold=0.50)
    # Optimized comparison at optimal threshold t*
    loss_opt, fp_opt, fn_opt, tp_opt = compute_financial_loss(y_test, probs_test, amounts_test, threshold=optimal_threshold)
    
    savings = loss_default - loss_opt
    savings_pct = (savings / loss_default) * 100.0 if loss_default > 0 else 0.0
    
    print(f"\n--- Financial Cost Matrix Results (Test Set) ---")
    print(f"  Default Threshold (t = 0.50):")
    print(f"    Total Loss:     ${loss_default:,.2f}")
    print(f"    False Positives: {fp_def}  (Friction cost: ${fp_def * 10.0:,.2f})")
    print(f"    False Negatives: {fn_def}  (Stolen money lost)")
    print(f"    True Positives:  {tp_def}")
    print(f"  Cost-Optimized Threshold (t* = {optimal_threshold:.4f}):")
    print(f"    Total Loss:     ${loss_opt:,.2f}")
    print(f"    False Positives: {fp_opt}")
    print(f"    False Negatives: {fn_opt}")
    print(f"    True Positives:  {tp_opt}")
    print(f"  Net Monetary Savings: ${savings:,.2f} ({savings_pct:.2f}% reduction in losses)")
    
    # Plot Cost vs Threshold Curve
    plt.figure(figsize=(7, 5))
    test_losses = [compute_financial_loss(y_test, probs_test, amounts_test, threshold=t)[0] for t in threshold_grid]
    plt.plot(threshold_grid, test_losses, label="Test Set Financial Loss ($)", color="#2c3e50")
    plt.axvline(x=0.50, color='gray', linestyle='--', label="Default Threshold (0.50)")
    plt.axvline(x=optimal_threshold, color='#e74c3c', linestyle='-', label=f"Optimal Threshold ({optimal_threshold:.3f})")
    plt.title("Financial Cost Curve vs. Classification Threshold")
    plt.xlabel("Probability Threshold")
    plt.ylabel("Total Expected Loss ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGS_DIR / "cost_optimization_curve.png")
    plt.close()

    # Save summary artifact
    summary = {
        "optimal_threshold": round(optimal_threshold, 4),
        "default_loss_usd": round(loss_default, 2),
        "optimized_loss_usd": round(loss_opt, 2),
        "monetary_savings_usd": round(savings, 2),
        "savings_percentage": round(savings_pct, 2),
        "fp_reduction": fp_def - fp_opt,
        "fn_reduction": fn_def - fn_opt
    }
    with open(ARTIFACTS_DIR / "cost_optimization_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        
    print(f"Saved artifacts to {ARTIFACTS_DIR / 'cost_optimization_summary.json'} and {FIGS_DIR / 'cost_optimization_curve.png'}")

if __name__ == "__main__":
    run()
