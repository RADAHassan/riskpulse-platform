import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import umap
from sklearn.metrics import silhouette_score

def run():
    print("[1/5] Loading test split and calibrated artifacts...")
    data = np.load("artifacts/data_splits.npz")
    X_test, y_test = data["X_test"], data["y_test"]

    base_xgb = joblib.load("artifacts/base_xgb.joblib")
    calibrator = joblib.load("artifacts/iso_calibrator.joblib")
    with open("artifacts/conformal.json", "r") as f:
        cfg = json.load(f)
    r_low, r_high = cfg["review_lower_bound"], cfg["review_upper_bound"]

    # Stratified visual sample: keep 100% of real test frauds (74) + 2500 legitimate transactions
    rng = np.random.default_rng(42)
    fraud_idx = np.where(y_test == 1)[0]
    legit_idx = np.where(y_test == 0)[0]
    sample_legit = rng.choice(legit_idx, size=2500, replace=False)
    selected_idx = np.concatenate([fraud_idx, sample_legit])
    rng.shuffle(selected_idx)

    X_sub = X_test[selected_idx]
    y_sub = y_test[selected_idx]

    # Predict with calibrated champion
    raw_p1 = base_xgb.predict_proba(X_sub)[:, 1]
    cal_p1 = calibrator.predict(raw_p1)
    preds = (cal_p1 >= 0.5).astype(int)
    is_review = (cal_p1 >= r_low) & (cal_p1 <= r_high)

    print("[2/5] Computing 2D projections (PCA, t-SNE, UMAP)...")
    # PCA with full components to generate explained variance curve
    pca_full = PCA(random_state=42).fit(X_sub)
    pca_2d = PCA(n_components=2, random_state=42)
    pca_coords = pca_2d.fit_transform(X_sub)

    tsne_coords = TSNE(n_components=2, perplexity=30, random_state=42).fit_transform(X_sub)
    umap_reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
    umap_coords = umap_reducer.fit_transform(X_sub)

    # Error classification
    err_types = []
    for i in range(len(y_sub)):
        yt, yp = int(y_sub[i]), int(preds[i])
        if yt == 1 and yp == 1: err_types.append("TP")
        elif yt == 0 and yp == 0: err_types.append("TN")
        elif yt == 0 and yp == 1: err_types.append("FP")
        else: err_types.append("FN")

    print("[3/5] Generating missing visual figures for report...")
    # 1. PCA Explained Variance Plot (viz_pca_variance.png)
    plt.figure(figsize=(6, 4))
    exp_var = np.cumsum(pca_full.explained_variance_ratio_)
    plt.plot(range(1, len(exp_var) + 1), exp_var, marker='o', color='#2c3e50')
    plt.axhline(y=0.90, color='r', linestyle='--', label='90% Variance Threshold')
    plt.title("Cumulative Explained Variance (PCA)")
    plt.xlabel("Number of Principal Components")
    plt.ylabel("Cumulative Variance Ratio")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("examples_output/viz_pca_variance.png")
    plt.close()

    # 2. Clusters & Outliers Plot (viz_clusters_outliers.png)
    plt.figure(figsize=(7, 6))
    colors = {0: "#3498db", 1: "#e74c3c"}
    labels = {0: "Legitimate", 1: "Fraud"}
    for lab in [0, 1]:
        mask = (y_sub == lab)
        plt.scatter(umap_coords[mask, 0], umap_coords[mask, 1], 
                    c=colors[lab], label=labels[lab], alpha=0.6, s=20 if lab==0 else 45)
    plt.title("UMAP Manifold Projection: Fraud vs. Legit")
    plt.xlabel("UMAP 1")
    plt.ylabel("UMAP 2")
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig("examples_output/viz_clusters_outliers.png")
    plt.close()

    # 3. Latent Error Breakdown Plot (viz_errors.png)
    plt.figure(figsize=(7, 6))
    err_colors = {"TN": "#bdc3c7", "TP": "#2ecc71", "FP": "#f39c12", "FN": "#e74c3c"}
    for et in ["TN", "TP", "FP", "FN"]:
        m = np.array([e == et for e in err_types])
        if np.sum(m) > 0:
            plt.scatter(umap_coords[m, 0], umap_coords[m, 1],
                        c=err_colors[et], label=et, alpha=0.7, s=25 if et=="TN" else 45)
    plt.title("Classification Error Distribution on UMAP Latent Space")
    plt.xlabel("UMAP 1")
    plt.ylabel("UMAP 2")
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig("examples_output/viz_errors.png")
    plt.close()

    # 4. Probability Heatmap Scatter (viz_probability.png)
    plt.figure(figsize=(7, 6))
    sc = plt.scatter(umap_coords[:, 0], umap_coords[:, 1], c=cal_p1, cmap="viridis", alpha=0.8, s=25)
    cbar = plt.colorbar(sc)
    cbar.set_label("Calibrated P(Fraud)")
    plt.title("Calibrated Posterior Risk Heatmap (UMAP)")
    plt.xlabel("UMAP 1")
    plt.ylabel("UMAP 2")
    plt.tight_layout()
    plt.savefig("examples_output/viz_probability.png")
    plt.close()

    print("[4/5] Computing embedding quality metrics...")
    sil = float(silhouette_score(umap_coords, y_sub))
    quality_df = pd.DataFrame([{
        "method": "UMAP",
        "silhouette_score": round(sil, 4),
        "pca_variance_2d": round(float(np.sum(pca_2d.explained_variance_ratio_)), 4)
    }])
    quality_df.to_csv("examples_output/embedding_quality.csv", index=False)

    print("[5/5] Exporting JSON artifacts for Dashboard & Meta...")
    payload = []
    for i in range(len(selected_idx)):
        payload.append({
            "id": int(selected_idx[i]),
            "true_label": int(y_sub[i]),
            "predicted_label": int(preds[i]),
            "fraud_probability": round(float(cal_p1[i]), 4),
            "is_uncertain": bool(is_review[i]),
            "review_required": bool(is_review[i]),
            "error_type": err_types[i],
            "pca_x": round(float(pca_coords[i, 0]), 4),
            "pca_y": round(float(pca_coords[i, 1]), 4),
            "tsne_x": round(float(tsne_coords[i, 0]), 4),
            "tsne_y": round(float(tsne_coords[i, 1]), 4),
            "umap_x": round(float(umap_coords[i, 0]), 4),
            "umap_y": round(float(umap_coords[i, 1]), 4)
        })

    with open("artifacts/latent_projections.json", "w") as f:
        json.dump(payload, f, indent=2)

    with open("examples_output/latent_projections.json", "w") as f:
        json.dump(payload, f, indent=2)

    meta = {
        "n_samples": len(payload),
        "n_frauds": int(np.sum(y_sub == 1)),
        "silhouette_score": round(sil, 4),
        "human_review_rate_pct": round(float(np.mean(is_review) * 100.0), 2)
    }
    with open("examples_output/latent_projections_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print("All visual figures and metrics successfully generated.")

if __name__ == "__main__":
    run()
