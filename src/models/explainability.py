import joblib
import json
import shap
import numpy as np
import pandas as pd
from src.config import ARTIFACTS_DIR
from src.data_prep import load_and_split_data

def run():
    print("[1/3] Loading hybrid model and test artifacts...")
    splits = load_and_split_data()
    X_test, y_test = splits["X_test"], splits["y_test"]
    
    # Load autoencoder to rebuild hybrid feature space
    ae = joblib.load(ARTIFACTS_DIR / "autoencoder.joblib")
    ae_test = ae.transform(X_test)
    X_test_aug = np.hstack([X_test, ae_test])
    
    feature_names = [f"V{i}" for i in range(1, 29)] + ["Hour_Sin", "Hour_Cos", "Scaled_Amount"]
    feature_names += ["AE_Recon_MSE"] + [f"AE_Latent_{i}" for i in range(8)]
    
    xgb_model = joblib.load(ARTIFACTS_DIR / "hybrid_xgb.joblib")
    calibrator = joblib.load(ARTIFACTS_DIR / "hybrid_iso_calibrator.joblib")
    
    print("[2/3] Computing TreeSHAP explanation values on test set...")
    explainer = shap.TreeExplainer(xgb_model)
    raw_probs = xgb_model.predict_proba(X_test_aug)[:, 1]
    cal_probs = calibrator.predict(raw_probs)
    
    # Isolate intercepted transactions (flagged at t* = 0.1442)
    flagged_idx = np.where(cal_probs >= 0.1442)[0]
    sample_to_explain = flagged_idx[:5]  # Explain first 5 declines
    
    shap_values = explainer.shap_values(X_test_aug[sample_to_explain])
    
    print("[3/3] Generating Adverse Action Reason Codes for Declines...")
    reasons_output = []
    for i, idx in enumerate(sample_to_explain):
        # Sort features by absolute contribution to the fraud score
        top_contrib_indices = np.argsort(np.abs(shap_values[i]))[::-1][:3]
        top_reasons = [
            {
                "feature": feature_names[col],
                "shap_impact": round(float(shap_values[i][col]), 4),
                "feature_value": round(float(X_test_aug[idx][col]), 4)
            }
            for col in top_contrib_indices
        ]
        
        record = {
            "transaction_index": int(idx),
            "calibrated_fraud_risk": round(float(cal_probs[idx]), 4),
            "ground_truth": int(y_test[idx]),
            "primary_decline_reasons": top_reasons
        }
        reasons_output.append(record)
        print(f"\nTransaction #{idx} | Risk: {cal_probs[idx]:.4f} | Ground Truth: {y_test[idx]}")
        for r in top_reasons:
            print(f"  -> {r['feature']} (Value: {r['feature_value']}, SHAP: {r['shap_impact']:+0.4f})")
            
    with open(ARTIFACTS_DIR / "sample_decline_reasons.json", "w") as f:
        json.dump(reasons_output, f, indent=2)
    print(f"\nReason codes saved to {ARTIFACTS_DIR / 'sample_decline_reasons.json'}")

if __name__ == "__main__":
    run()
