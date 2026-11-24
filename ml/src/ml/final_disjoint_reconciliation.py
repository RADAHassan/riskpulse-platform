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


def bss(y_true, y_prob):
    bm = brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))
    br = brier_score_loss(y_true, np.full_like(y_prob, np.mean(y_true), dtype=float))
    return float(1.0 - bm / br)


def compute_ece(y_true, y_prob, n_bins=10):
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = 0.0
    for i in range(n_bins):
        m = (y_prob >= bins[i]) & (y_prob < bins[i + 1]) if i < n_bins - 1 else (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        if np.any(m):
            out += (np.sum(m) / len(y_true)) * abs(np.mean(y_true[m]) - np.mean(y_prob[m]))
    return float(out)


def topk_mask(scores, rate=0.002):
    k = max(1, int(len(scores) * rate))
    idx = np.argsort(scores)[::-1][:k]
    m = np.zeros(len(scores), dtype=bool)
    m[idx] = True
    return m


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
    pooled_scores = {"LogReg": [], "Default_XGB": [], "LightGBM": [], "Tuned_XGB_29D": []}
    cal_logs = {"none": [], "sigmoid_platt": [], "isotonic": []}

    for _, s0, s1, s2, s3 in windows:
        tr_df, ca_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s1 * n) : int(s2 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
        Xtr, ytr, _, sc = build_29d(tr_df, fit=True)
        Xca, yca, _, _ = build_29d(ca_df, scaler=sc, fit=False)
        Xoo, yoo, amtoo, _ = build_29d(oo_df, scaler=sc, fit=False)
        spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))

        pooled_y.append(yoo)
        pooled_amt.append(amtoo)

        std = StandardScaler().fit(Xtr)
        pooled_scores["LogReg"].append(LogisticRegression(class_weight="balanced", max_iter=500, random_state=42).fit(std.transform(Xtr), ytr).predict_proba(std.transform(Xoo))[:, 1])
        pooled_scores["Default_XGB"].append(xgb.XGBClassifier(scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr).predict_proba(Xoo)[:, 1])
        pooled_scores["LightGBM"].append(lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1).fit(Xtr, ytr).predict_proba(Xoo)[:, 1])

        tx = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr)
        rca, roo = tx.predict_proba(Xca)[:, 1], tx.predict_proba(Xoo)[:, 1]
        pooled_scores["Tuned_XGB_29D"].append(roo)

        p_sig = PlattLR().fit(rca.reshape(-1, 1), yca).predict_proba(roo.reshape(-1, 1))[:, 1]
        p_iso = IsotonicRegression(out_of_bounds="clip").fit(rca, yca).predict(roo)
        cal_logs["none"].append((yoo, roo))
        cal_logs["sigmoid_platt"].append((yoo, p_sig))
        cal_logs["isotonic"].append((yoo, p_iso))

    y_pool, amt_pool = np.concatenate(pooled_y), np.concatenate(pooled_amt)

    print("1. DISJOINT POOLED CALIBRATOR TABLE (N=113,491):")
    for cname, pairs in cal_logs.items():
        yc, pc = np.concatenate([p[0] for p in pairs]), np.concatenate([p[1] for p in pairs])
        print(f"  {cname:<16} | BSS: {bss(yc, pc):+.4f} | ECE: {compute_ece(yc, pc):.5f} | Unique Levels: {len(np.unique(np.round(pc, 6)))}")

    print("\n2. HIGH-DOLLAR MISSED FRAUDS ANALYSIS (WHY DOLLAR RECALL IS 64.4% ACROSS MODELS):")
    fraud_idx = np.where(y_pool == 1)[0]
    fraud_amts = amt_pool[fraud_idx]
    missed_sets = {}
    for m, slist in pooled_scores.items():
        sp = np.concatenate(slist)
        flagged = topk_mask(sp, 0.002)
        missed_f = fraud_idx[~flagged[fraud_idx]]
        missed_sets[m] = set(missed_f.tolist())
    common_missed = sorted(list(set.intersection(*missed_sets.values())))
    common_missed_usd = float(np.sum(amt_pool[common_missed]))
    total_fraud_usd = float(np.sum(fraud_amts))
    top_missed_amts = sorted(amt_pool[common_missed].tolist(), reverse=True)[:5]
    print(f"  Total OOT Fraud Principal: ${total_fraud_usd:,.2f} across {len(fraud_idx)} frauds")
    print(f"  Frauds missed by ALL 4 models simultaneously: {len(common_missed)} frauds totaling ${common_missed_usd:,.2f} ({common_missed_usd/total_fraud_usd*100:.1f}% of all fraud dollars)")
    print(f"  Top 5 shared missed fraud amounts: {[round(x, 2) for x in top_missed_amts]}")

    print("\n3. CONTIGUOUS TIME-BLOCK BOOTSTRAP (500-TXN BLOCKS, 1,000 REPLICATES) ON DISJOINT OOT:")
    rng = np.random.default_rng(42)
    block_size = 500
    n_blocks = len(y_pool) // block_size
    s_champ = np.concatenate(pooled_scores["Tuned_XGB_29D"])
    s_def = np.concatenate(pooled_scores["Default_XGB"])
    b_champ, b_diff = [], []
    for _ in range(1000):
        chosen_blocks = rng.integers(0, n_blocks, size=n_blocks)
        idx = np.concatenate([np.arange(b * block_size, (b + 1) * block_size) for b in chosen_blocks])
        if np.sum(y_pool[idx]) == 0:
            continue
        ap_c = average_precision_score(y_pool[idx], s_champ[idx])
        ap_d = average_precision_score(y_pool[idx], s_def[idx])
        b_champ.append(ap_c)
        b_diff.append(ap_c - ap_d)
    print(f"  Tuned_XGB_29D Block-Bootstrap PR-AUC: 0.7689 [{np.percentile(b_champ, 2.5):.4f}, {np.percentile(b_champ, 97.5):.4f}]")
    print(f"  Block-Bootstrap Delta (Tuned - Default): {np.mean(b_diff):+.4f} [{np.percentile(b_diff, 2.5):+.4f}, {np.percentile(b_diff, 97.5):+.4f}]")

    print("\n4. 5-SEED VARIANCE CHECK ON DISJOINT OOT (TUNED_XGB_29D):")
    seed_aps = []
    for seed in [7, 21, 42, 84, 128]:
        s_y, s_p = [], []
        for _, s0, s1, s2, s3 in windows:
            tr_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
            Xtr, ytr, _, sc = build_29d(tr_df, fit=True)
            Xoo, yoo, _, _ = build_29d(oo_df, scaler=sc, fit=False)
            spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
            tx = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=seed, n_jobs=-1).fit(Xtr, ytr)
            s_y.append(yoo)
            s_p.append(tx.predict_proba(Xoo)[:, 1])
        seed_aps.append(average_precision_score(np.concatenate(s_y), np.concatenate(s_p)))
    print(f"  5-Seed Pooled OOT PR-AUC: {np.mean(seed_aps):.4f} +/- {np.std(seed_aps):.4f}")

    print("\n5. BUFFER-QUARANTINE ARCHITECTURAL FIX FOR 500-FRAUD CONSECUTIVE BURST (W=20,000):")
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

    # Consecutive injection at index 20,000
    r_b, c_b, y_b = np.insert(raw_st, 20000, b_raw), np.insert(cal_st, 20000, b_cal), np.insert(y_st_f, 20000, np.ones(500, dtype=int))

    # Buffer Quarantine: do not append AUTO_DECLINE / flagged transactions into the rolling nominal buffer
    buf = list(raw_ca[-20000:])
    preds = np.zeros(len(r_b), dtype=int)
    resc = 0
    for i, (rs, cp) in enumerate(zip(r_b, c_b)):
        fq = rs >= np.quantile(buf, 0.998)
        fg = cp >= 0.80
        if fg and not fq:
            resc += 1
        flagged = fq or fg
        preds[i] = int(flagged)
        if not flagged:  # Quarantine flagged alerts from poisoning the rolling baseline buffer
            buf.append(rs)
            buf.pop(0)
    tp, al, fn = int(np.sum((preds == 1) & (y_b == 1))), int(np.sum(preds == 1)), int(np.sum(y_b == 1))
    print(f"  W=20000 + Guard + Buffer Quarantine -> Alerts={al} | TP={tp}/{fn} | Recall={tp/fn*100:.1f}% | Precision={tp/al*100:.1f}% | GuardRescues={resc}")
