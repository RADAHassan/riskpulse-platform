import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression as PlattLR
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.calibration import calibration_curve

warnings.filterwarnings("ignore")


def build_29d(df_slice: pd.DataFrame, scaler=None, fit: bool = False):
    v_mat = df_slice[[f"V{i}" for i in range(1, 29)]].values
    amt_raw = df_slice["Amount"].values
    if fit:
        scaler = RobustScaler()
        amt_scaled = scaler.fit_transform(amt_raw.reshape(-1, 1))
    else:
        amt_scaled = scaler.transform(amt_raw.reshape(-1, 1))
    return np.hstack([amt_scaled, v_mat]), df_slice["Class"].values.astype(int), amt_raw, scaler


def rec_at_fpr(y_true, scores, target_fpr):
    thr = np.quantile(scores[y_true == 0], 1.0 - target_fpr)
    return float(np.sum((scores >= thr) & (y_true == 1)) / np.sum(y_true == 1) * 100.0)


def metrics_at_rate(y_true, scores, amounts, rate=0.002):
    k = max(1, int(len(y_true) * rate))
    top_k = np.argsort(scores)[::-1][:k]
    pred = np.zeros(len(y_true), dtype=int)
    pred[top_k] = 1
    tp = int(np.sum((pred == 1) & (y_true == 1)))
    return float(tp / np.sum(y_true == 1) * 100.0), float(tp / k * 100.0), float(np.sum(amounts[(pred == 1) & (y_true == 1)]) / np.sum(amounts[y_true == 1]) * 100.0)


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv") if Path("data/creditcard.csv").exists() else next(Path(".").rglob("creditcard.csv"))
    df = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True).drop_duplicates(keep="first").reset_index(drop=True)
    n = len(df)

    params_29 = {
        "n_estimators": 220, "max_depth": 3, "learning_rate": 0.10228931953949602,
        "min_child_weight": 11.229391545284763, "subsample": 0.9948677176835029,
        "colsample_bytree": 0.8689073040163973, "reg_lambda": 0.7019215213261507, "gamma": 1.7417867332281343,
    }
    windows = [("W1", 0.0, 0.50, 0.60, 0.73), ("W2", 0.0, 0.60, 0.73, 0.86), ("W3", 0.0, 0.73, 0.86, 1.00)]

    pooled_y, pooled_amt = [], []
    scores = {k: [] for k in ["LogReg_29D", "LightGBM_29D", "Tuned_XGB_29D", "LogAmtWeighted_XGB_29D", "LinearAmtWeighted_XGB_29D"]}
    cal_raw, cal_platt, cal_iso = [], [], []

    for _, s0, s1, s2, s3 in windows:
        tr_df, ca_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s1 * n) : int(s2 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
        Xtr, ytr, amttr, sc = build_29d(tr_df, fit=True)
        Xca, yca, _, _ = build_29d(ca_df, scaler=sc, fit=False)
        Xoo, yoo, amtoo, _ = build_29d(oo_df, scaler=sc, fit=False)
        spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
        pooled_y.append(yoo)
        pooled_amt.append(amtoo)

        std = StandardScaler().fit(Xtr)
        scores["LogReg_29D"].append(LogisticRegression(class_weight="balanced", max_iter=500, random_state=42).fit(std.transform(Xtr), ytr).predict_proba(std.transform(Xoo))[:, 1])
        scores["LightGBM_29D"].append(lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1).fit(Xtr, ytr).predict_proba(Xoo)[:, 1])

        tx = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr)
        rca, roo = tx.predict_proba(Xca)[:, 1], tx.predict_proba(Xoo)[:, 1]
        scores["Tuned_XGB_29D"].append(roo)
        cal_raw.append(roo)
        cal_platt.append(PlattLR().fit(rca.reshape(-1, 1), yca).predict_proba(roo.reshape(-1, 1))[:, 1])
        cal_iso.append(IsotonicRegression(out_of_bounds="clip").fit(rca, yca).predict(roo))

        w_log = np.where(ytr == 1, spw * (1.0 + np.log1p(amttr) / np.mean(np.log1p(amttr))), 1.0)
        scores["LogAmtWeighted_XGB_29D"].append(xgb.XGBClassifier(**params_29, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr, sample_weight=w_log).predict_proba(Xoo)[:, 1])

        amt_clip = np.clip(amttr, 0.0, 1000.0)
        w_lin = np.where(ytr == 1, spw * (1.0 + amt_clip / np.mean(amt_clip)), 1.0)
        scores["LinearAmtWeighted_XGB_29D"].append(xgb.XGBClassifier(**params_29, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr, sample_weight=w_lin).predict_proba(Xoo)[:, 1])

    y_pool, amt_pool = np.concatenate(pooled_y), np.concatenate(pooled_amt)

    # Exact same 6,000-txn hourly block bootstrap (seed=42, 1,000 replicates)
    rng = np.random.default_rng(42)
    block_size = 6000
    n_blocks = len(y_pool) // block_size
    boot_idx = []
    for _ in range(1000):
        chosen = rng.integers(0, n_blocks, size=n_blocks)
        idx = np.concatenate([np.arange(b * block_size, (b + 1) * block_size) for b in chosen])
        if np.sum(y_pool[idx]) > 0:
            boot_idx.append(idx)

    s_champ = np.concatenate(scores["Tuned_XGB_29D"])
    champ_b = np.array([average_precision_score(y_pool[idx], s_champ[idx]) for idx in boot_idx])

    print("1. MISSING TABLE 1 METRICS (HOURLY BLOCK BOOTSTRAP, 6,000-TXN BLOCKS):")
    for m in ["LogAmtWeighted_XGB_29D", "LinearAmtWeighted_XGB_29D"]:
        sp = np.concatenate(scores[m])
        ap = average_precision_score(y_pool, sp)
        r005, r010 = rec_at_fpr(y_pool, sp, 0.0005), rec_at_fpr(y_pool, sp, 0.0010)
        rc, pc, dr = metrics_at_rate(y_pool, sp, amt_pool, 0.002)
        b_ap = np.array([average_precision_score(y_pool[idx], sp[idx]) for idx in boot_idx])
        b_rc = np.array([metrics_at_rate(y_pool[idx], sp[idx], amt_pool[idx], 0.002)[0] for idx in boot_idx])
        diff = champ_b - b_ap
        print(
            f"  {m:<26} | PR-AUC: {ap:.4f} [{np.percentile(b_ap,2.5):.4f}, {np.percentile(b_ap,97.5):.4f}] | "
            f"Rec@0.05%FPR: {r005:.1f}% | Rec@0.1%FPR: {r010:.1f}% | "
            f"Rec@0.2%: {rc:.1f}% [{np.percentile(b_rc,2.5):.1f}%, {np.percentile(b_rc,97.5):.1f}%] | "
            f"Prec: {pc:.1f}% | DollarRec: {dr:.1f}% | Delta={np.mean(diff):+.4f} [{np.percentile(diff,2.5):+.4f}, {np.percentile(diff,97.5):+.4f}]"
        )

    # 2. Generate the two clean diagnostic figures
    Path("figures").mkdir(exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    # Figure 1: Precision-Recall Curves (3 Model Families)
    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=200)
    for label, key, color in [
        ("Tuned XGBoost 29D (PR-AUC = 0.7689)", "Tuned_XGB_29D", "#1b4f72"),
        ("Logistic Regression 29D (PR-AUC = 0.7358)", "LogReg_29D", "#d35400"),
        ("LightGBM 29D (PR-AUC = 0.7302)", "LightGBM_29D", "#229954"),
    ]:
        p, r, _ = precision_recall_curve(y_pool, np.concatenate(scores[key]))
        ax.plot(r, p, lw=2.0, label=label, color=color)
    ax.set_xlabel("Recall", fontsize=10)
    ax.set_ylabel("Precision", fontsize=10)
    ax.set_title("Disjoint Pooled OOT Precision-Recall Curves (N = 113,491; 131 Frauds)", fontsize=10.5, fontweight="bold")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower left", frameon=True, fontsize=8.5)
    fig.tight_layout()
    fig.savefig("figures/fig_pr_curves.png")
    plt.close(fig)

    # Figure 2: Reliability Diagram (Uncalibrated vs Platt vs Isotonic)
    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=200)
    ax.plot([0, 1], [0, 1], "k--", lw=1.2, label="Perfect Calibration")
    for label, probs, color, marker in [
        ("Uncalibrated Raw (BSS = -0.7164)", np.concatenate(cal_raw), "#c0392b", "o"),
        ("Platt Scaling (BSS = +0.4767)", np.concatenate(cal_platt), "#2980b9", "s"),
        ("Isotonic Regression (BSS = +0.6390)", np.concatenate(cal_iso), "#1e8449", "^"),
    ]:
        fop, mpv = calibration_curve(y_pool, np.clip(probs, 0, 1), n_bins=10, strategy="uniform")
        ax.plot(mpv, fop, marker=marker, lw=1.8, markersize=5, label=label, color=color)
    ax.set_xlabel("Mean Predicted Probability", fontsize=10)
    ax.set_ylabel("Observed Fraud Fraction", fontsize=10)
    ax.set_title("Disjoint OOT Calibration Reliability Diagram (Tuned XGBoost 29D)", fontsize=10.5, fontweight="bold")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.05)
    ax.legend(loc="upper left", frameon=True, fontsize=8.5)
    fig.tight_layout()
    fig.savefig("figures/fig_reliability.png")
    plt.close(fig)
    print("2. SAVED FIGURES: figures/fig_pr_curves.png and figures/fig_reliability.png")
