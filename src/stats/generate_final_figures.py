import joblib
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.manifold import TSNE
import umap

from src.config import ARTIFACTS_DIR, RANDOM_STATE
from src.data_prep import load_and_split_data

OUT_DIR = Path("examples_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("[1/4] Loading test data and hybrid model artifacts...")
splits = load_and_split_data()
X_test, y_test = splits["X_test"], splits["y_test"]

ae = joblib.load(ARTIFACTS_DIR / "autoencoder.joblib")
ae_test = ae.transform(X_test)
X_test_aug = np.hstack([X_test, ae_test])

xgb = joblib.load(ARTIFACTS_DIR / "hybrid_xgb.joblib")
cal = joblib.load(ARTIFACTS_DIR / "hybrid_iso_calibrator.joblib")

raw_probs = xgb.predict_proba(X_test_aug)[:, 1]
cal_probs = cal.predict(raw_probs)
preds = (cal_probs >= 0.1442).astype(int)

print("[2/4] Computing 2D UMAP projection on the augmented hybrid space...")
# Subsample for smooth 2D rendering (keep all frauds + 2,000 non-frauds)
fraud_mask = (y_test == 1)
non_fraud_indices = np.where(~fraud_mask)[0]
np.random.seed(RANDOM_STATE)
sample_non_fraud = np.random.choice(non_fraud_indices, size=2000, replace=False)
sample_idx = np.concatenate([np.where(fraud_mask)[0], sample_non_fraud])

X_sample = X_test_aug[sample_idx]
y_sample = y_test[sample_idx]
probs_sample = cal_probs[sample_idx]
preds_sample = preds[sample_idx]

reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, random_state=RANDOM_STATE)
embedding = reducer.fit_transform(X_sample)

print("[3/4] Generating and overwriting visual figures...")

# 1. Calibrated Fraud Probability Map
plt.figure(figsize=(8, 6))
scatter = plt.scatter(embedding[:, 0], embedding[:, 1], c=probs_sample, cmap='viridis', s=18, alpha=0.8)
plt.colorbar(scatter, label='Calibrated Fraud Probability (P)')
plt.title('Hybrid Model: Calibrated Risk Space (UMAP 2D Projection)')
plt.xlabel('UMAP Dimension 1')
plt.ylabel('UMAP Dimension 2')
plt.tight_layout()
plt.savefig(OUT_DIR / "viz_probability.png", dpi=300)
plt.close()

# 2. Confusion / Error Analysis Map at t* = 0.1442
# TP: Green, FN: Red, FP: Orange, TN: Light Gray
colors = []
for actual, pred in zip(y_sample, preds_sample):
    if actual == 1 and pred == 1:
        colors.append("#2ca02c") # TP
    elif actual == 1 and pred == 0:
        colors.append("#d62728") # FN
    elif actual == 0 and pred == 1:
        colors.append("#ff7f0e") # FP
    else:
        colors.append("#d3d3d3") # TN

plt.figure(figsize=(8, 6))
plt.scatter(embedding[:, 0], embedding[:, 1], c=colors, s=18, alpha=0.85)
# Add dummy markers for legend
plt.scatter([], [], c="#2ca02c", label="True Positive (Caught)")
plt.scatter([], [], c="#d62728", label="False Negative (Missed)")
plt.scatter([], [], c="#ff7f0e", label="False Positive (Friction)")
plt.scatter([], [], c="#d3d3d3", label="True Negative (Legit)")
plt.legend(loc="upper right")
plt.title("Hybrid Decision Boundary Performance at t* = 0.1442")
plt.xlabel('UMAP Dimension 1')
plt.ylabel('UMAP Dimension 2')
plt.tight_layout()
plt.savefig(OUT_DIR / "viz_errors.png", dpi=300)
plt.close()

# 3. Autoencoder Reconstruction Error Distribution
plt.figure(figsize=(8, 5))
recon_errors = ae_test[:, 0]
plt.hist(recon_errors[y_test == 0], bins=50, alpha=0.6, label='Legitimate (Y=0)', density=True, color='blue')
plt.hist(recon_errors[y_test == 1], bins=50, alpha=0.6, label='Fraudulent (Y=1)', density=True, color='red')
plt.yscale('log')
plt.xlabel('Autoencoder Reconstruction MSE')
plt.ylabel('Density (Log Scale)')
plt.title('Unsupervised Anomaly Separation (Reconstruction Error)')
plt.legend()
plt.tight_layout()
plt.savefig(OUT_DIR / "viz_ae_separation.png", dpi=300)
plt.close()

print(f"[4/4] Successfully updated final figures in {OUT_DIR}/")
