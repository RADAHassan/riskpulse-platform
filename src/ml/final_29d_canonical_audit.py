import time
import hashlib
import warnings
import joblib
import numpy as np
import pandas as pd
import optuna
import xgboost as xgb
import lightgbm as lgb
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression as PlattLR
from sklearn.metrics import average_precision_score, brier_score_loss
from src.models.autoencoder import AutoencoderFeatureExtractor

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)


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
    h_sin = np.sin(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    h_cos = np.cos(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    return np.hstack([X29, h_sin, h_cos]), y, amt_raw, scaler


def bss(y_true, y_prob):
    bm = brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))
    br = brier_score_loss(y_true, np.full_like(y_prob, np.mean(y_true), dtype=float))
    return float(1.0 - bm / br)


def ece(y_true, y_prob, n_bins=10):
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = 0.0
    for i in range(n_bins):
        m = (y_prob >= bins[i]) & (y_prob < bins[i + 1]) if i < n_bins - 1 else (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        if np.any(m):
            out += (np.sum(m) / len(y_true)) * abs(np.mean(y_true[m]) - np.mean(y_prob[m]))
    return float(out)


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


def tune_strict_pre_oot(df_pre: pd.DataFrame, include_hour=False, n_trials=25):
    """Strict expanding-window CV inside [0%, 50%] — zero overlap with any calibration or OOT window."""
    n = len(df_pre)
    folds = [(0.0, 0.50, 0.67), (0.0, 0.67, 0.84), (0.0, 0.84, 1.00)]
    fn = build_31d if include_hour else build_29d
    cache = []
    for s0, s1, s2 in folds:
        Xtr, ytr, _, sc = fn(df_pre.iloc[int(s0 * n) : int(s1 * n)], fit=True)
        Xva, yva, _, _ = fn(df_pre.iloc[int(s1 * n) : int(s2 * n)], scaler=sc, fit=False)
        cache.append((Xtr, ytr, Xva, yva))

    def obj(trial):
        p = {
            "n_estimators": trial.suggest_int("n_estimators", 120, 350),
            "max_depth": trial.suggest_int("max_depth", 3, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 15.0),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 2.0),
        }
        aps = []
        for Xtr, ytr, Xva, yva in cache:
            spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
            m = xgb.XGBClassifier(**p, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr)
            aps.append(average_precision_score(yva, m.predict_proba(Xva)[:, 1]))
        return float(np.mean(aps))

    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    st.optimize(obj, n_trials=n_trials)
    return st.best_params


def compute_psi(exp, act, bins=10):
    cuts = np.percentile(exp, np.linspace(0, 100, bins + 1))
    cuts[0], cuts[-1] = -np.inf, np.inf
    ec = np.clip(np.histogram(exp, bins=cuts)[0] / len(exp), 1e-6, None)
    ac = np.clip(np.histogram(act, bins=cuts)[0] / len(act), 1e-6, None)
    return float(np.sum((ac - ec) * np.log(ac / ec)))


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv") if Path("data/creditcard.csv").exists() else next(Path(".").rglob("creditcard.csv"))
    df_raw = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True)
    # Exact row deduplication (all 31 columns: Time, V1..V28, Amount, Class)
    df = df_raw.drop_duplicates(keep="first").reset_index(drop=True)
    print(f"1. EXACT DEDUPLICATION: {len(df_raw):,} -> {len(df):,} rows ({len(df_raw)-len(df):,} exact duplicates removed; {int(df['Class'].sum())} frauds remaining)")

    n = len(df)
    # Strict pre-OOT tuning block [0%, 50%] — completely disjoint from all OOT evaluation horizons [60%, 100%]
    params_29 = tune_strict_pre_oot(df.iloc[: int(0.50 * n)], include_hour=False, n_trials=25)
    params_31 = tune_strict_pre_oot(df.iloc[: int(0.50 * n)], include_hour=True, n_trials=25)
    print(f"2. STRICT PRE-OOT [0%-50%] OPTUNA PARAMS (29D): {params_29}")

    windows = [
        ("Window 1 (24.5h->34.2h)", 0.0, 0.50, 0.60, 0.73),
        ("Window 2 (34.2h->41.4h)", 0.0, 0.60, 0.73, 0.86),
        ("Window 3 (41.4h->48.0h)", 0.0, 0.70, 0.85, 1.00),
    ]
    models = ["LogReg_29D", "Default_XGB_29D", "LightGBM_29D", "Tuned_XGB_29D (No Hour)", "Tuned_XGB_31D (With Hour)"]
    pooled_y, pooled_amt = [], []
    pooled_scores = {m: [] for m in models}
    cal_logs = {"none": [], "sigmoid_platt": [], "isotonic": []}
    per_win_29 = []

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
        lr = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42).fit(std.transform(Xtr29), ytr)
        pooled_scores["LogReg_29D"].append(lr.predict_proba(std.transform(Xoo29))[:, 1])

        dxgb = xgb.XGBClassifier(scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr)
        pooled_scores["Default_XGB_29D"].append(dxgb.predict_proba(Xoo29)[:, 1])

        lgbm = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1).fit(Xtr29, ytr)
        pooled_scores["LightGBM_29D"].append(lgbm.predict_proba(Xoo29)[:, 1])

        tx29 = xgb.XGBClassifier(**params_29, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr)
        rca29 = tx29.predict_proba(Xca29)[:, 1]
        roo29 = tx29.predict_proba(Xoo29)[:, 1]
        pooled_scores["Tuned_XGB_29D (No Hour)"].append(roo29)

        tx31 = xgb.XGBClassifier(**params_31, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr31, ytr)
        pooled_scores["Tuned_XGB_31D (With Hour)"].append(tx31.predict_proba(Xoo31)[:, 1])

        platt = PlattLR().fit(rca29.reshape(-1, 1), yca)
        p_sig = platt.predict_proba(roo29.reshape(-1, 1))[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(rca29, yca)
        p_iso = iso.predict(roo29)

        cal_logs["none"].append((yoo, roo29))
        cal_logs["sigmoid_platt"].append((yoo, p_sig))
        cal_logs["isotonic"].append((yoo, p_iso))

        ap_w = average_precision_score(yoo, roo29)
        r_w, pr_w, dr_w = metrics_at_rate(yoo, roo29, amtoo, 0.002)
        per_win_29.append((label, len(yoo), int(np.sum(yoo)), ap_w, r_w, pr_w, dr_w, bss(yoo, p_iso), bss(yoo, p_sig)))

    print("\n3. PER-WINDOW OOT RESULTS FOR CHAMPION 29D (NO HOUR):")
    for row in per_win_29:
        print(f"  {row[0]} | N={row[1]:,} (Frauds={row[2]}) | PR-AUC={row[3]:.4f} | Rec@0.2%={row[4]:.1f}% | Prec@0.2%={row[5]:.1f}% | DollarRec={row[6]:.1f}% | IsoBSS={row[7]:.4f} | PlattBSS={row[8]:.4f}")

    y_pool = np.concatenate(pooled_y)
    amt_pool = np.concatenate(pooled_amt)
    print(f"\n4. POOLED OOT BENCHMARK (N={len(y_pool):,}, Frauds={int(np.sum(y_pool))}) + PAIRED BOOTSTRAP DELTAS vs Tuned_XGB_29D:")
    rng = np.random.default_rng(42)
    boot_idx = [rng.integers(0, len(y_pool), size=len(y_pool)) for _ in range(1000)]

    s_champ = np.concatenate(pooled_scores["Tuned_XGB_29D (No Hour)"])
    champ_boot_ap = np.array([average_precision_score(y_pool[idx], s_champ[idx]) for idx in boot_idx if np.sum(y_pool[idx]) > 0])

    for m in models:
        sp = np.concatenate(pooled_scores[m])
        ap_f = average_precision_score(y_pool, sp)
        r005 = rec_at_fpr(y_pool, sp, 0.0005)
        r010 = rec_at_fpr(y_pool, sp, 0.0010)
        rc, pc, dr = metrics_at_rate(y_pool, sp, amt_pool, 0.002)
        b_ap = np.array([average_precision_score(y_pool[idx], sp[idx]) for idx in boot_idx if np.sum(y_pool[idx]) > 0])
        b_rc = np.array([metrics_at_rate(y_pool[idx], sp[idx], amt_pool[idx], 0.002)[0] for idx in boot_idx if np.sum(y_pool[idx]) > 0])
        if m == "Tuned_XGB_29D (No Hour)":
            delta_str = "Reference Champion"
        else:
            diff = champ_boot_ap - b_ap
            delta_str = f"Delta={np.mean(diff):+.4f} [{np.percentile(diff, 2.5):+.4f}, {np.percentile(diff, 97.5):+.4f}]"
        print(
            f"  {m:<26} | PR-AUC: {ap_f:.4f} [{np.percentile(b_ap,2.5):.4f}, {np.percentile(b_ap,97.5):.4f}] | "
            f"Rec@0.05%FPR: {r005:.1f}% | Rec@0.1%FPR: {r010:.1f}% | Rec@0.2%: {rc:.1f}% [{np.percentile(b_rc,2.5):.1f}%, {np.percentile(b_rc,97.5):.1f}%] | "
            f"Prec@0.2%: {pc:.1f}% | DollarRec: {dr:.1f}% | {delta_str}"
        )

    print("\n5. CALIBRATOR COMPARISON ON POOLED OOT (29D):")
    for cname, pairs in cal_logs.items():
        yc = np.concatenate([p[0] for p in pairs])
        pc = np.concatenate([p[1] for p in pairs])
        print(f"  {cname:<16} | Pooled BSS: {bss(yc, pc):+.4f} | Pooled ECE: {ece(yc, pc):.5f} | Unique Levels: {len(np.unique(np.round(pc, 6)))}")

    # 6. Stream Replay on 29D (60% -> 100%) + W=20k Burst Test (using boundary/borderline frauds with calibrated prob in [0.40, 0.85] + extreme frauds)
    X_tr_f, y_tr_f, _, sc_f = build_29d(df.iloc[: int(0.50 * n)], fit=True)
    X_ca_f, y_ca_f, _, _ = build_29d(df.iloc[int(0.50 * n) : int(0.60 * n)], scaler=sc_f, fit=False)
    X_st_f, y_st_f, _, _ = build_29d(df.iloc[int(0.60 * n) :], scaler=sc_f, fit=False)

    spw_f = float(np.sum(y_tr_f == 0) / np.sum(y_tr_f == 1))
    clf_f = xgb.XGBClassifier(**params_29, scale_pos_weight=spw_f, eval_metric="logloss", random_state=42, n_jobs=-1).fit(X_tr_f, y_tr_f)
    iso_f = IsotonicRegression(out_of_bounds="clip").fit(clf_f.predict_proba(X_ca_f)[:, 1], y_ca_f)
    platt_f = PlattLR().fit(clf_f.predict_proba(X_ca_f)[:, 1].reshape(-1, 1), y_ca_f)

    raw_ca = clf_f.predict_proba(X_ca_f)[:, 1]
    raw_st = clf_f.predict_proba(X_st_f)[:, 1]
    cal_st = iso_f.predict(raw_st)

    def run_replay(r_init, r_stream, c_stream, y_stream, W, guard=True):
        buf = list(r_init[-W:])
        preds = np.zeros(len(r_stream), dtype=int)
        rescues = 0
        for i, (rs, cp) in enumerate(zip(r_stream, c_stream)):
            fq = rs >= np.quantile(buf, 0.998)
            fg = guard and (cp >= 0.80)
            if fg and not fq:
                rescues += 1
            preds[i] = int(fq or fg)
            buf.append(rs)
            if len(buf) > W:
                buf.pop(0)
        tp = int(np.sum((preds == 1) & (y_stream == 1)))
        al = int(np.sum(preds == 1))
        fn = int(np.sum(y_stream == 1))
        return al / len(y_stream) * 100.0, al, tp, fn, tp / fn * 100.0, tp / max(1, al) * 100.0, rescues

    print(f"\n6. LIVE-STREAM REPLAY (60%->100%, N={len(y_st_f):,}, Frauds={int(np.sum(y_st_f))}):")
    for W in [1000, 5000, 20000]:
        rate, al, tp, fn, rec, prec, resc = run_replay(raw_ca, raw_st, cal_st, y_st_f, W=W, guard=True)
        print(f"  W={W:<6} | Rate={rate:.3f}% ({al} alerts) | TP={tp}/{fn} | Recall={rec:.1f}% | Precision={prec:.1f}% | GuardRescues={resc}")

    # Synthetic burst: 80 jittered frauds (Gaussian noise sigma=0.35 added to real stream frauds to simulate novel attack variants) injected at index 20,000
    rng_b = np.random.default_rng(42)
    real_frauds_X = X_st_f[y_st_f == 1]
    sampled_X = real_frauds_X[rng_b.choice(len(real_frauds_X), size=80, replace=True)] + rng_b.normal(0, 0.35, size=(80, 29))
    burst_raw = clf_f.predict_proba(sampled_X)[:, 1]
    burst_cal = iso_f.predict(burst_raw)

    r_b_stream = np.insert(raw_st, 20000, burst_raw)
    c_b_stream = np.insert(cal_st, 20000, burst_cal)
    y_b_stream = np.insert(y_st_f, 20000, np.ones(80, dtype=int))

    print(f"\n7. JITTERED SYNTHETIC FRAUD BURST TEST (80 Perturbed Frauds Injected; Total Frauds={int(np.sum(y_b_stream))}):")
    for W in [1000, 20000]:
        for gd in [False, True]:
            rate, al, tp, fn, rec, prec, resc = run_replay(raw_ca, r_b_stream, c_b_stream, y_b_stream, W=W, guard=gd)
            lbl = f"W={W:<5} {'+ Guard (P>=0.80)' if gd else 'ONLY (No Guard)  '}"
            print(f"  {lbl} -> Alerts={al} | TP={tp}/{fn} | Recall={rec:.1f}% | Precision={prec:.1f}% | GuardRescues={resc}")

    # 8. Measure exact single-transaction latency for 29D Champion (depth=3, 232 trees)
    lat_ms = []
    for i in range(1000):
        row_x = X_st_f[i : i + 1]
        t0 = time.perf_counter()
        rs = clf_f.predict_proba(row_x)[:, 1]
        _ = iso_f.predict(rs)
        lat_ms.append((time.perf_counter() - t0) * 1000.0)
    print(f"\n8. MEASURED 29D IN-PROCESS LATENCY (1,000 SEQUENTIAL CALLS): p50={np.percentile(lat_ms,50):.3f} ms | p95={np.percentile(lat_ms,95):.3f} ms | p99={np.percentile(lat_ms,99):.3f} ms")
