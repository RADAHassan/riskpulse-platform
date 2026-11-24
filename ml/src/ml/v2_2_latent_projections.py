"""
RiskPulse v2.3.8 — Task 7: Reproducible Latent Space Projections (PCA, t-SNE, UMAP)
Computes 2D embeddings on a stratified subsample of the deduplicated 29D OOT test set
([60%, 100%]) using log1p(Amount) + RobustScaler to prevent outlier collapse, aligns
review highlighting with Task 4's causal Top-0.5% raw-score router (human_review)
plus FP/FN error markers, and exports:
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
from sklearn.preprocessing import RobustScaler
import umap
import xgboost as xgb

warnings.filterwarnings("ignore")

SEED = 42
N_LEGIT_SUBSAMPLE = 2500
ALERT_BUDGET = 0.002
REVIEW_BUDGET = 0.005


def main():
    Path("artifacts/figures").mkdir(parents=True, exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    feature_cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all = df[feature_cols].values.copy()
    y_all = df["Class"].values
    n = len(df)

    # Train on [0%, 50%], calibrate on [50%, 60%], evaluate on OOT [60%, 100%]
    tr_end, cal_end = int(0.50 * n), int(0.60 * n)
    X_tr, y_tr = X_all[:tr_end], y_all[:tr_end]
    X_cal, y_cal = X_all[tr_end:cal_end], y_all[tr_end:cal_end]
    X_oot, y_oot = X_all[cal_end:], y_all[cal_end:]

    import joblib
    bundle = joblib.load("artifacts/riskpulse_29d_bundle.joblib")
    params = bundle["xgb_model"].get_params()
    params.update({"random_state": SEED, "n_jobs": -1})
    model = xgb.XGBClassifier(**params)
    model.fit(X_tr, y_tr)
    raw_cal = model.predict_proba(X_cal)[:, 1]
    raw_oot = model.predict_proba(X_oot)[:, 1]

    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_cal, y_cal)
    p_oot = iso.predict(raw_oot)

    # Task 4 causal Top-0.5% human_review router + 0.20% operating threshold (calibrated on [50%, 60%])
    thr_op = float(np.quantile(raw_cal, 1.0 - ALERT_BUDGET))
    review_threshold = float(np.quantile(raw_cal, 1.0 - REVIEW_BUDGET))

    alert_oot = raw_oot >= thr_op
    human_review_oot = raw_oot >= review_threshold
    is_fp_oot = alert_oot & (y_oot == 0)
    is_fn_oot = (~alert_oot) & (y_oot == 1)

    # Stratified subsample: ALL OOT frauds + ALL human_review cases + 2,500 random clear legits
    rng = np.random.default_rng(SEED)
    fraud_idx = np.where(y_oot == 1)[0]
    review_legit_idx = np.where((y_oot == 0) & human_review_oot)[0]
    clear_legit_idx = np.where((y_oot == 0) & (~human_review_oot))[0]
    sampled_legit = rng.choice(clear_legit_idx, size=min(N_LEGIT_SUBSAMPLE, len(clear_legit_idx)), replace=False)

    sub_idx = np.unique(np.concatenate([fraud_idx, review_legit_idx, sampled_legit]))
    X_sub_raw = X_oot[sub_idx].copy()
    X_sub_raw[:, 0] = np.log1p(np.maximum(X_sub_raw[:, 0], 0.0))
    X_sub = RobustScaler().fit_transform(X_sub_raw)

    y_sub = y_oot[sub_idx]
    s_sub = raw_oot[sub_idx]
    p_sub = p_oot[sub_idx]
    r_sub = human_review_oot[sub_idx]
    fp_sub = is_fp_oot[sub_idx]
    fn_sub = is_fn_oot[sub_idx]

    true_prev_pct = float(y_oot.mean() * 100.0)
    sub_prev_pct = float(y_sub.mean() * 100.0)
    true_rev_pct = float(human_review_oot.mean() * 100.0)
    sub_rev_pct = float(r_sub.mean() * 100.0)

    print(
        f"Computing PCA, t-SNE, UMAP on N={len(sub_idx):,} OOT subsample "
        f"(frauds={int(y_sub.sum())}: {sub_prev_pct:.2f}% vs {true_prev_pct:.2f}% true; "
        f"human_review={int(r_sub.sum())}: {sub_rev_pct:.2f}% vs {true_rev_pct:.2f}% true; "
        f"FP={int(fp_sub.sum())}, FN={int(fn_sub.sum())})..."
    )

    pca = PCA(n_components=2, random_state=SEED)
    emb_pca = pca.fit_transform(X_sub)

    tsne = TSNE(n_components=2, perplexity=30, init="pca", learning_rate="auto", random_state=SEED)
    emb_tsne = tsne.fit_transform(X_sub)

    reducer = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, random_state=SEED)
    emb_umap = reducer.fit_transform(X_sub)

    metrics = {}
    for name, emb in [("pca", emb_pca), ("tsne", emb_tsne), ("umap", emb_umap)]:
        tw = float(trustworthiness(X_sub, emb, n_neighbors=15))
        sil = float(silhouette_score(emb, y_sub))
        metrics[name] = {
            "trustworthiness_k15": round(tw, 4),
            "silhouette_fraud_vs_legit": round(sil, 4),
        }
    metrics["pca"]["explained_variance_ratio"] = [round(float(v), 4) for v in pca.explained_variance_ratio_]

    records = []
    for i in range(len(sub_idx)):
        records.append({
            "oot_index": int(sub_idx[i]),
            "true_label": int(y_sub[i]),
            "raw_score": round(float(s_sub[i]), 6),
            "fraud_probability": round(float(p_sub[i]), 5),
            "human_review": bool(r_sub[i]),
            "is_fp": bool(fp_sub[i]),
            "is_fn": bool(fn_sub[i]),
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
            "scaling": "log1p(Amount) + RobustScaler across 29D features",
            "oot_total_n": int(len(y_oot)),
            "oot_true_fraud_prevalence_pct": round(true_prev_pct, 3),
            "oot_true_human_review_pct": round(true_rev_pct, 3),
            "subsample_n": int(len(sub_idx)),
            "subsample_frauds": int(y_sub.sum()),
            "subsample_human_reviews": int(r_sub.sum()),
            "subsample_fp": int(fp_sub.sum()),
            "subsample_fn": int(fn_sub.sum()),
            "subsample_fraud_prevalence_pct": round(sub_prev_pct, 2),
            "subsample_human_review_pct": round(sub_rev_pct, 2),
            "router_policy": {
                "method": "top_0.5pct_raw_score",
                "thr_op_cal": round(thr_op, 6),
                "review_threshold_cal": round(review_threshold, 6),
            },
        },
        "quality_metrics": metrics,
        "points": records,
    }
    with open("artifacts/latent_projections.json", "w") as f:
        json.dump(out, f, indent=2)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6), dpi=150)
    x_lo, x_hi = np.percentile(emb_pca[:, 0], [1.0, 99.0])
    n_x_clipped = int(((emb_pca[:, 0] < x_lo) | (emb_pca[:, 0] > x_hi)).sum())
    panels = [
        (emb_pca, f"PCA (Trust={metrics['pca']['trustworthiness_k15']:.3f}, Sil={metrics['pca']['silhouette_fraud_vs_legit']:.3f}; {n_x_clipped} x-outliers clipped)", "PC1 (1st-99th pct)", "PC2", True),
        (emb_tsne, f"t-SNE (Trust={metrics['tsne']['trustworthiness_k15']:.3f}, Sil={metrics['tsne']['silhouette_fraud_vs_legit']:.3f})", "t-SNE 1", "t-SNE 2", False),
        (emb_umap, f"UMAP (Trust={metrics['umap']['trustworthiness_k15']:.3f}, Sil={metrics['umap']['silhouette_fraud_vs_legit']:.3f})", "UMAP 1", "UMAP 2", False),
    ]

    legit_clear = (y_sub == 0) & (~r_sub) & (~fp_sub)
    rev_non_err = r_sub & (~fp_sub) & (~fn_sub) & (y_sub == 0)
    tp_m = (y_sub == 1) & (~fn_sub)

    for ax, (emb, title, xl, yl, clip_axes) in zip(axes, panels):
        ax.scatter(emb[legit_clear, 0], emb[legit_clear, 1], c="#94a3b8", s=8, alpha=0.30, label="Legitimate")
        ax.scatter(emb[rev_non_err, 0], emb[rev_non_err, 1], c="#f59e0b", s=22, marker="^", alpha=0.80, edgecolor="black", linewidth=0.3, label="Human Review (Marginal Band)")
        ax.scatter(emb[tp_m, 0], emb[tp_m, 1], c="#16a34a", s=24, alpha=0.90, edgecolor="black", linewidth=0.3, label="Detected Fraud (TP)")
        ax.scatter(emb[fp_sub, 0], emb[fp_sub, 1], c="#ea580c", s=34, marker="X", edgecolor="black", linewidth=0.4, label="False Positive (FP)")
        ax.scatter(emb[fn_sub, 0], emb[fn_sub, 1], c="#dc2626", s=42, marker="D", edgecolor="black", linewidth=0.5, label="Missed Fraud (FN)")
        if clip_axes:
            ax.set_xlim(x_lo, x_hi)
        ax.set_title(title, fontsize=10.5, fontweight="bold")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.grid(alpha=0.2)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, fontsize=9.5)
    fig.suptitle(
        f"29D OOT Latent Projections (log1p + RobustScaler, N={len(sub_idx):,}) — "
        f"Human Reviews: {int(r_sub.sum())} ({true_rev_pct:.2f}% OOT) | FP: {int(fp_sub.sum())} | FN: {int(fn_sub.sum())}",
        fontsize=11,
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
