import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score

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


def build_31d(df_slice: pd.DataFrame, scaler=None, fit: bool = False):
    X29, y, amt_raw, scaler = build_29d(df_slice, scaler=scaler, fit=fit)
    hour = (df_slice["Time"].values / 3600.0) % 24.0
    return np.hstack([X29, np.sin(2.0 * np.pi * hour / 24.0).reshape(-1, 1), np.cos(2.0 * np.pi * hour / 24.0).reshape(-1, 1)]), y, amt_raw, scaler


def metrics_at_rate(y_true, scores, amounts, rate=0.002):
    k = max(1, int(len(y_true) * rate))
    top_k = np.argsort(scores)[::-1][:k]
    pred = np.zeros(len(y_true), dtype=int)
    pred[top_k] = 1
    tp = int(np.sum((pred == 1) & (y_true == 1)))
    rec = tp / np.sum(y_true == 1) * 100.0
    prec = tp / k * 100.0
    d_rec = np.sum(amounts[(pred == 1) & (y_true == 1)]) / np.sum(amounts[y_true == 1]) * 100.0
    return float(rec), float(prec), float(d_rec)


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv") if Path("data/creditcard.csv").exists() else next(Path(".").rglob("creditcard.csv"))
    df = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True).drop_duplicates(keep="first").reset_index(drop=True)
    n = len(df)

    params_29 = {
        "n_estimators": 220, "max_depth": 3, "learning_rate": 0.10228931953949602,
        "min_child_weight": 11.229391545284763, "subsample": 0.9948677176835029,
        "colsample_bytree": 0.8689073040163973, "reg_lambda": 0.7019215213261507, "gamma": 1.7417867332281343,
    }
    params_31 = {
        "n_estimators": 232, "max_depth": 3, "learning_rate": 0.0738,
        "min_child_weight": 11.54, "subsample": 0.6266,
        "colsample_bytree": 0.8186, "reg_lambda": 4.835, "gamma": 1.364,
    }
    windows = [("W1", 0.0, 0.50, 0.60, 0.73), ("W2", 0.0, 0.60, 0.73, 0.86), ("W3", 0.0, 0.73, 0.86, 1.00)]

    models = ["LogReg_29D", "Default_XGB_29D", "LightGBM_29D", "Tuned_XGB_29D", "Tuned_XGB_31D", "AmtWeighted_XGB_29D"]
    pooled_y, pooled_amt = [], []
    pooled_scores = {m: [] for m in models}

    for _, s0, s1, s2, s3 in windows:
        tr_df, ca_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s1 * n) : int(s2 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
        Xtr29, ytr, amttr, sc29 = build_29d(tr_df, fit=True)
        Xoo29, yoo, amtoo, _ = build_29d(oo_df, scaler=sc29, fit=False)
        Xtr31, _, _, sc31 = build_31d(tr_df, fit=True)
        Xoo31, _, _, _ = build_31d(oo_df, scaler=sc31, fit=False)

        spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
        pooled_y.append(yoo)
        pooled_amt.append(amtoo)

        std = StandardScaler().fit(Xtr29)
        pooled_scores["LogReg_29D"].append(LogisticRegression(class_weight="balanced", max_iter=500, random_state=42).fit(std.transform(Xtr29), ytr).predict_proba(std.transform(Xoo29))[:, 1])
        pooled_scores["Default_XGB_29D"].append(xgb.XGBClassifier(scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr).predict_proba(Xoo29)[:, 1])
        pooled_scores["LightGBM_29D"].append(lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1).fit(Xtr29, ytr).predict_proba(Xoo29)[:, 1])
        pooled_scores["Tuned_XGB_29D"].append(xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr).predict_proba(Xoo29)[:, 1])
        pooled_scores["Tuned_XGB_31D"].append(xgb.XGBClassifier(**params_31, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr31, ytr).predict_proba(Xoo31)[:, 1])

        # Direct test: Amount-weighted sample weights (log1p(Amount) * class imbalance weight)
        w_amt = np.where(ytr == 1, spw * (1.0 + np.log1p(amttr) / np.mean(np.log1p(amttr))), 1.0)
        pooled_scores["AmtWeighted_XGB_29D"].append(xgb.XGBClassifier(**params_29, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr, sample_weight=w_amt).predict_proba(Xoo29)[:, 1])

    y_pool, amt_pool = np.concatenate(pooled_y), np.concatenate(pooled_amt)

    print("1. HOURLY BLOCK BOOTSTRAP (6,000-TXN BLOCKS ≈ 1 HR, 1,000 REPLICATES) + AMOUNT-WEIGHTED TEST:")
    rng = np.random.default_rng(42)
    block_size = 6000
    n_blocks = len(y_pool) // block_size
    boot_idx = []
    for _ in range(1000):
        chosen = rng.integers(0, n_blocks, size=n_blocks)
        idx = np.concatenate([np.arange(b * block_size, (b + 1) * block_size) for b in chosen])
        if np.sum(y_pool[idx]) > 0:
            boot_idx.append(idx)

    s_champ = np.concatenate(pooled_scores["Tuned_XGB_29D"])
    champ_b = np.array([average_precision_score(y_pool[idx], s_champ[idx]) for idx in boot_idx])

    for m in models:
        sp = np.concatenate(pooled_scores[m])
        ap_f = average_precision_score(y_pool, sp)
        rc, pc, dr = metrics_at_rate(y_pool, sp, amt_pool, 0.002)
        b_ap = np.array([average_precision_score(y_pool[idx], sp[idx]) for idx in boot_idx])
        b_rc = np.array([metrics_at_rate(y_pool[idx], sp[idx], amt_pool[idx], 0.002)[0] for idx in boot_idx])
        d_str = "Reference" if m == "Tuned_XGB_29D" else f"Delta={np.mean(champ_b - b_ap):+.4f} [{np.percentile(champ_b - b_ap, 2.5):+.4f}, {np.percentile(champ_b - b_ap, 97.5):+.4f}]"
        print(f"  {m:<20} | PR-AUC: {ap_f:.4f} [{np.percentile(b_ap,2.5):.4f}, {np.percentile(b_ap,97.5):.4f}] | Rec@0.2%: {rc:.1f}% [{np.percentile(b_rc,2.5):.1f}%, {np.percentile(b_rc,97.5):.1f}%] | Prec: {pc:.1f}% | DollarRec: {dr:.1f}% | {d_str}")

    print("\n2. QUARANTINE STABILITY ON NORMAL STREAM & GUARD-ONLY QUARANTINE ON 500-FRAUD BURST (W=20,000):")
    X_tr_f, y_tr_f, _, sc_f = build_29d(df.iloc[: int(0.50 * n)], fit=True)
    X_ca_f, y_ca_f, _, _ = build_29d(df.iloc[int(0.50 * n) : int(0.60 * n)], scaler=sc_f, fit=False)
    X_st_f, y_st_f, _, _ = build_29d(df.iloc[int(0.60 * n) :], scaler=sc_f, fit=False)
    spw_f = float(np.sum(y_tr_f == 0) / np.sum(y_tr_f == 1))
    clf_f = xgb.XGBClassifier(**params_29, scale_pos_weight=spw_f, eval_metric="logloss", random_state=42, n_jobs=-1).fit(X_tr_f, y_tr_f)
    iso_f = IsotonicRegression(out_of_bounds="clip").fit(clf_f.predict_proba(X_ca_f)[:, 1], y_ca_f)
    raw_ca, raw_st = clf_f.predict_proba(X_ca_f)[:, 1], clf_f.predict_proba(X_st_f)[:, 1]
    cal_st = iso_f.predict(raw_st)

    rng_b = np.random.default_rng(42)
    real_frauds_X = X_st_f[y_st_f == 1]
    sampled_X = real_frauds_X[rng_b.choice(len(real_frauds_X), size=500, replace=True)] + rng_b.normal(0, 0.35, size=(500, 29))
    b_raw, b_cal = clf_f.predict_proba(sampled_X)[:, 1], iso_f.predict(clf_f.predict_proba(sampled_X)[:, 1])

    r_b, c_b, y_b = np.insert(raw_st, 20000, b_raw), np.insert(cal_st, 20000, b_cal), np.insert(y_st_f, 20000, np.ones(500, dtype=int))

    def eval_policy(r_seq, c_seq, y_seq, mode="standard"):
        buf = list(raw_ca[-20000:])
        preds = np.zeros(len(r_seq), dtype=int)
        for i, (rs, cp) in enumerate(zip(r_seq, c_seq)):
            fq = rs >= np.quantile(buf, 0.998)
            fg = cp >= 0.80
            flagged = fq or fg
            preds[i] = int(flagged)
            if mode == "standard":
                buf.append(rs); buf.pop(0)
            elif mode == "quarantine_all":
                if not flagged:
                    buf.append(rs); buf.pop(0)
            elif mode == "quarantine_guard_only":
                if not fg:  # Exclude only P_cal >= 0.80 high-confidence burst transactions; normal 0.2% tail still refreshes buffer
                    buf.append(rs); buf.pop(0)
        tp, al, fn = int(np.sum((preds == 1) & (y_seq == 1))), int(np.sum(preds == 1)), int(np.sum(y_seq == 1))
        return al, al / len(y_seq) * 100.0, tp, fn, tp / fn * 100.0, tp / max(1, al) * 100.0

    for stream_name, r_s, c_s, y_s in [("Normal Stream (N=113,491)", raw_st, cal_st, y_st_f), ("500-Fraud Burst (N=113,991)", r_b, c_b, y_b)]:
        for mode in ["standard", "quarantine_all", "quarantine_guard_only"]:
            al, rate, tp, fn, rec, prec = eval_policy(r_s, c_s, y_s, mode=mode)
            print(f"  {stream_name:<27} | {mode:<21} -> Alerts={al:<4} ({rate:.3f}%) | TP={tp}/{fn} | Recall={rec:.1f}% | Precision={prec:.1f}%")
