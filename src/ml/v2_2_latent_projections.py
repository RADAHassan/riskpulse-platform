"""
RiskPulse v2.2 — Task 7: Reproducible Latent Space Projections (PCA, t-SNE, UMAP)
Computes 2D embeddings on a stratified subsample of the deduplicated 29D OOT test set
([60%, 100%]), evaluates Trustworthiness and Silhouette scores, and exports:
  - artifacts/latent_projections.json
  - artifacts/figures/pca_tsne_umap.png
"""
import json
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.isotonic import IsotonicRegression
from sklearn.manifold import TSNE, trustworthiness
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
import umap
import xgboost as xgb

warnings.filterwarnings("ignore")

SEED = 42
N_LEGIT_SUBSAMPLE = 2500


def main():
    Path("artifacts/figures").mkdir(parents=True, exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    feature_cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all = df[feature_cols].values
    y_all = df["Class"].values
    n = len(df)

    # Train on [0%, 50%], calibrate on [50%, 60%], evaluate on OOT [60%, 100%]
    tr_end, cal_end = int(0.50 * n), int(0.60 * n)
    X_tr, y_tr = X_all[:tr_end], y_all[:tr_end]
    X_cal, y_cal = X_all[tr_end:cal_end], y_all[tr_end:cal_end]
    X_oot, y_oot = X_all[cal_end:], y_all[cal_end:]

    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=220,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        eval_metric="logloss",
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(model.predict_proba(X_cal)[:, 1], y_cal)
    p_oot = iso.predict(model.predict_proba(X_oot)[:, 1])

    # Two-tier uncertainty band: uncertain cases routed to manual review (0.05 <= P_cal < 0.80)
    is_uncertain_oot = (p_oot >= 0.05) & (p_oot < 0.80)

    # Stratified subsample for tractable t-SNE / UMAP visualization:
    # Keep ALL OOT frauds + ALL uncertain boundary cases + 2,500 random legitimate cases
    rng = np.random.default_rng(SEED)
    fraud_idx = np.where(y_oot == 1)[0]
    uncert_legit_idx = np.where((y_oot == 0) & is_uncertain_oot)[0]
    clear_legit_idx = np.where((y_oot == 0) & (~is_uncertain_oot))[0]
    sampled_legit = rng.choice(clear_legit_idx, size=min(N_LEGIT_SUBSAMPLE, len(clear_legit_idx)), replace=False)

    sub_idx = np.unique(np.concatenate([fraud_idx, uncert_legit_idx, sampled_legit]))
    X_sub = StandardScaler().fit_transform(X_oot[sub_idx])
    y_sub = y_oot[sub_idx]
    p_sub = p_oot[sub_idx]
    u_sub = is_uncertain_oot[sub_idx]

    true_prev_pct = float(y_oot.mean() * 100.0)
    sub_prev_pct = float(y_sub.mean() * 100.0)
    print(f"Computing PCA, t-SNE, UMAP on N={len(sub_idx):,} OOT subsample ({int(y_sub.sum())} frauds, {sub_prev_pct:.2f}% vs {true_prev_pct:.2f}% true OOT)...")

    pca = PCA(n_components=2, random_state=SEED)
    emb_pca = pca.fit_transform(X_sub)

    tsne = TSNE(n_components=2, perplexity=30, init="pca", learning_rate="auto", random_state=SEED)
    emb_tsne = tsne.fit_transform(X_sub)

    reducer = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, random_state=SEED)
    emb_umap = reducer.fit_transform(X_sub)

    # Quantitative embedding quality metrics
    metrics = {}
    for name, emb in [("pca", emb_pca), ("tsne", emb_tsne), ("umap", emb_umap)]:
        tw = float(trustworthiness(X_sub, emb, n_neighbors=15))
        sil = float(silhouette_score(emb, y_sub))
        metrics[name] = {
            "trustworthiness_k15": round(tw, 4),
            "silhouette_fraud_vs_legit": round(sil, 4),
        }
    metrics["pca"]["explained_variance_ratio"] = [round(float(v), 4) for v in pca.explained_variance_ratio_]

    # Save JSON artifact
    records = []
    for i in range(len(sub_idx)):
        records.append({
            "oot_index": int(sub_idx[i]),
            "true_label": int(y_sub[i]),
            "fraud_probability": round(float(p_sub[i]), 5),
            "is_uncertain": bool(u_sub[i]),
            "pca_x": round(float(emb_pca[i, 0]), 4),
            "pca_y": round(float(emb_pca[i, 1]), 4),
            "tsne_x": round(float(emb_tsne[i, 0]), 4),
            "tsne_y": round(float(emb_tsne[i, 1]), 4),
            "umap_x": round(float(emb_umap[i, 0]), 4),
            "umap_y": round(float(emb_umap[i, 1]), 4),
        })

    out = {
        "metadata": {
            "seed": SEED,
            "oot_total_n": int(len(y_oot)),
            "oot_true_fraud_prevalence_pct": round(true_prev_pct, 3),
            "subsample_n": int(len(sub_idx)),
            "subsample_frauds": int(y_sub.sum()),
            "subsample_uncertain": int(u_sub.sum()),
            "subsample_fraud_prevalence_pct": round(sub_prev_pct, 2),
            "uncertainty_band": [0.05, 0.80],
        },
        "quality_metrics": metrics,
        "points": records,
    }
    with open("artifacts/latent_projections.json", "w") as f:
        json.dump(out, f, indent=2)

    # Plot 3-panel figure with quantitative metrics & subsample disclosure
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), dpi=150)
    panels = [
        (emb_pca, f"PCA (Trust={metrics['pca']['trustworthiness_k15']:.3f}, Sil={metrics['pca']['silhouette_fraud_vs_legit']:.3f})", "PC1", "PC2"),
        (emb_tsne, f"t-SNE (Trust={metrics['tsne']['trustworthiness_k15']:.3f}, Sil={metrics['tsne']['silhouette_fraud_vs_legit']:.3f})", "t-SNE 1", "t-SNE 2"),
        (emb_umap, f"UMAP (Trust={metrics['umap']['trustworthiness_k15']:.3f}, Sil={metrics['umap']['silhouette_fraud_vs_legit']:.3f})", "UMAP 1", "UMAP 2"),
    ]

    legit_m = (y_sub == 0) & (~u_sub)
    fraud_m = (y_sub == 1) & (~u_sub)
    uncert_m = u_sub

    for ax, (emb, title, xl, yl) in zip(axes, panels):
        ax.scatter(emb[legit_m, 0], emb[legit_m, 1], c="#94a3b8", s=8, alpha=0.35, label="Legitimate")
        ax.scatter(emb[fraud_m, 0], emb[fraud_m, 1], c="#dc2626", s=18, alpha=0.85, label="Fraud")
        ax.scatter(emb[uncert_m, 0], emb[uncert_m, 1], c="#f59e0b", s=26, marker="^", edgecolor="black", linewidth=0.4, label="Uncertain (0.05 ≤ P < 0.80)")
        ax.set_title(title, fontsize=10.5, fontweight="bold")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.grid(alpha=0.2)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=10)
    fig.suptitle(
        f"29D OOT Latent Projections — Stratified Subsample (N={len(sub_idx):,}; {int(y_sub.sum())} frauds = {sub_prev_pct:.1f}% plotted vs. {true_prev_pct:.2f}% true OOT)",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0.06, 1, 0.93])
    plt.savefig("artifacts/figures/pca_tsne_umap.png", dpi=150)
    plt.close()

    print("\n=== EMBEDDING QUALITY METRICS ===")
    print(json.dumps(metrics, indent=2))
    print("Saved: artifacts/latent_projections.json & artifacts/figures/pca_tsne_umap.png")


if __name__ == "__main__":
    main()
