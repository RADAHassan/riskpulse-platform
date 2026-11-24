import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression as PlattLR
from sklearn.metrics import average_precision_score, brier_score_loss

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


def bss(y_true, y_prob):
    bm = brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))
    br = brier_score_loss(y_true, np.full_like(y_prob, np.mean(y_true), dtype=float))
    return float(1.0 - bm / br)


def rec_at_fpr(y_true, scores, target_fpr):
    thr = np.quantile(scores[y_true == 0], 1.0 - target_fpr)
    return float(np.sum((scores >= thr) & (y_true == 1)) / np.sum(y_true == 1) * 100.0)


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

    # Pre-OOT [0%, 50%] Optuna-selected 29D parameters
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

    # STRICTLY DISJOINT OOT EVALUATION WINDOWS: [0.60, 0.73), [0.73, 0.86), [0.86, 1.00]
    windows = [
        ("Window 1", 0.0, 0.50, 0.60, 0.73),
        ("Window 2", 0.0, 0.60, 0.73, 0.86),
        ("Window 3", 0.0, 0.73, 0.86, 1.00),
    ]

    models = ["LogReg_29D", "Default_XGB_29D", "LightGBM_29D", "Tuned_XGB_29D", "Tuned_XGB_31D"]
    pooled_y, pooled_amt = [], []
    pooled_scores = {m: [] for m in models}
    cal_logs = {"none": [], "sigmoid_platt": [], "isotonic": []}

    print("1. STRICTLY DISJOINT PER-WINDOW OOT RESULTS (29D):")
    for label, s0, s1, s2, s3 in windows:
        tr_df, ca_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s1 * n) : int(s2 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
        Xtr29, ytr, _, sc29 = build_29d(tr_df, fit=True)
        Xca29, yca, _, _ = build_29d(ca_df, scaler=sc29, fit=False)
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

        tx29 = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr)
        rca29, roo29 = tx29.predict_proba(Xca29)[:, 1], tx29.predict_proba(Xoo29)[:, 1]
        pooled_scores["Tuned_XGB_29D"].append(roo29)
        pooled_scores["Tuned_XGB_31D"].append(xgb.XGBClassifier(**params_31, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr31, ytr).predict_proba(Xoo31)[:, 1])

        p_sig = PlattLR().fit(rca29.reshape(-1, 1), yca).predict_proba(roo29.reshape(-1, 1))[:, 1]
        p_iso = IsotonicRegression(out_of_bounds="clip").fit(rca29, yca).predict(roo29)
        cal_logs["none"].append((yoo, roo29))
        cal_logs["sigmoid_platt"].append((yoo, p_sig))
        cal_logs["isotonic"].append((yoo, p_iso))

        ap_w = average_precision_score(yoo, roo29)
        r_w, pr_w, dr_w = metrics_at_rate(yoo, roo29, amtoo, 0.002)
        print(f"  {label} [{s2:.2f}->{s3:.2f}] | N={len(yoo):,} (Frauds={int(np.sum(yoo))}) | PR-AUC={ap_w:.4f} | Rec@0.2%={r_w:.1f}% | Prec@0.2%={pr_w:.1f}% | DollarRec={dr_w:.1f}% | IsoBSS={bss(yoo, p_iso):.4f}")

    y_pool, amt_pool = np.concatenate(pooled_y), np.concatenate(pooled_amt)
    print(f"\n2. DISJOINT POOLED OOT BENCHMARK (N={len(y_pool):,}, Frauds={int(np.sum(y_pool))}) + PAIRED BOOTSTRAP DELTAS:")
    rng = np.random.default_rng(42)
    boot_idx = [rng.integers(0, len(y_pool), size=len(y_pool)) for _ in range(1000)]
    s_champ = np.concatenate(pooled_scores["Tuned_XGB_29D"])
    champ_b = np.array([average_precision_score(y_pool[idx], s_champ[idx]) for idx in boot_idx if np.sum(y_pool[idx]) > 0])

    for m in models:
        sp = np.concatenate(pooled_scores[m])
        ap_f = average_precision_score(y_pool, sp)
        r005, r010 = rec_at_fpr(y_pool, sp, 0.0005), rec_at_fpr(y_pool, sp, 0.0010)
        rc, pc, dr = metrics_at_rate(y_pool, sp, amt_pool, 0.002)
        b_ap = np.array([average_precision_score(y_pool[idx], sp[idx]) for idx in boot_idx if np.sum(y_pool[idx]) > 0])
        b_rc = np.array([metrics_at_rate(y_pool[idx], sp[idx], amt_pool[idx], 0.002)[0] for idx in boot_idx if np.sum(y_pool[idx]) > 0])
        d_str = "Reference" if m == "Tuned_XGB_29D" else f"Delta={np.mean(champ_b - b_ap):+.4f} [{np.percentile(champ_b - b_ap, 2.5):+.4f}, {np.percentile(champ_b - b_ap, 97.5):+.4f}]"
        print(f"  {m:<16} | PR-AUC: {ap_f:.4f} [{np.percentile(b_ap,2.5):.4f}, {np.percentile(b_ap,97.5):.4f}] | Rec@0.05%FPR: {r005:.1f}% | Rec@0.1%FPR: {r010:.1f}% | Rec@0.2%: {rc:.1f}% [{np.percentile(b_rc,2.5):.1f}%, {np.percentile(b_rc,97.5):.1f}%] | Prec@0.2%: {pc:.1f}% | DollarRec: {dr:.1f}% | {d_str}")

    print("\n3. DISJOINT POOLED CALIBRATOR BSS (29D):")
    for cname, pairs in cal_logs.items():
        yc, pc = np.concatenate([p[0] for p in pairs]), np.concatenate([p[1] for p in pairs])
        print(f"  {cname:<16} | Pooled BSS: {bss(yc, pc):+.4f}")

    # 4. Stress-test W=20,000 with a 500-fraud sustained burst (2.5% of buffer, >12x the 0.20% quantile)
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
    b_raw = clf_f.predict_proba(sampled_X)[:, 1]
    b_cal = iso_f.predict(b_raw)

    r_b, c_b, y_b = np.insert(raw_st, 20000, b_raw), np.insert(cal_st, 20000, b_cal), np.insert(y_st_f, 20000, np.ones(500, dtype=int))
    print(f"\n4. HEAVY 500-FRAUD SUSTAINED BURST STRESS TEST ON W=20,000 (Total Frauds={int(np.sum(y_b))}):")
    for gd in [False, True]:
        buf = list(raw_ca[-20000:])
        preds = np.zeros(len(r_b), dtype=int)
        resc = 0
        for i, (rs, cp) in enumerate(zip(r_b, c_b)):
            fq = rs >= np.quantile(buf, 0.998)
            fg = gd and (cp >= 0.80)
            if fg and not fq:
                resc += 1
            preds[i] = int(fq or fg)
            buf.append(rs)
            buf.pop(0)
        tp, al, fn = int(np.sum((preds == 1) & (y_b == 1))), int(np.sum(preds == 1)), int(np.sum(y_b == 1))
        print(f"  W=20000 {'+ Guard (P>=0.80)' if gd else 'ONLY (No Guard)  '} -> Alerts={al} | TP={tp}/{fn} | Recall={tp/fn*100:.1f}% | Precision={tp/al*100:.1f}% | GuardRescues={resc}")
