import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.preprocessing import RobustScaler
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
    windows = [("W1", 0.0, 0.50, 0.60, 0.73), ("W2", 0.0, 0.60, 0.73, 0.86), ("W3", 0.0, 0.73, 0.86, 1.00)]

    pooled_y, pooled_amt, s_log, s_lin = [], [], [], []
    for _, s0, s1, s2, s3 in windows:
        tr_df, oo_df = df.iloc[int(s0 * n) : int(s1 * n)], df.iloc[int(s2 * n) : int(s3 * n)]
        Xtr, ytr, amttr, sc = build_29d(tr_df, fit=True)
        Xoo, yoo, amtoo, _ = build_29d(oo_df, scaler=sc, fit=False)
        spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
        pooled_y.append(yoo)
        pooled_amt.append(amtoo)

        w_log = np.where(ytr == 1, spw * (1.0 + np.log1p(amttr) / np.mean(np.log1p(amttr))), 1.0)
        s_log.append(xgb.XGBClassifier(**params_29, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr, sample_weight=w_log).predict_proba(Xoo)[:, 1])

        amt_clip = np.clip(amttr, 0.0, 1000.0)
        w_lin = np.where(ytr == 1, spw * (1.0 + amt_clip / np.mean(amt_clip)), 1.0)
        s_lin.append(xgb.XGBClassifier(**params_29, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr, ytr, sample_weight=w_lin).predict_proba(Xoo)[:, 1])

    y_pool, amt_pool = np.concatenate(pooled_y), np.concatenate(pooled_amt)
    for label, sp in [("LogAmtWeighted_XGB_29D (1-3x)", np.concatenate(s_log)), ("LinearAmtWeighted_XGB_29D (capped $1k)", np.concatenate(s_lin))]:
        rc, pc, dr = metrics_at_rate(y_pool, sp, amt_pool, 0.002)
        print(f"1. {label:<38} -> PR-AUC={average_precision_score(y_pool, sp):.4f} | Rec@0.2%={rc:.1f}% | Prec@0.2%={pc:.1f}% | DollarRec={dr:.1f}%")

    # 2. Independent Burst Check: 1,000 jittered frauds injected late at index 65,000
    X_tr_f, y_tr_f, _, sc_f = build_29d(df.iloc[: int(0.50 * n)], fit=True)
    X_ca_f, y_ca_f, _, _ = build_29d(df.iloc[int(0.50 * n) : int(0.60 * n)], scaler=sc_f, fit=False)
    X_st_f, y_st_f, _, _ = build_29d(df.iloc[int(0.60 * n) :], scaler=sc_f, fit=False)
    spw_f = float(np.sum(y_tr_f == 0) / np.sum(y_tr_f == 1))
    clf_f = xgb.XGBClassifier(**params_29, scale_pos_weight=spw_f, eval_metric="logloss", random_state=42, n_jobs=-1).fit(X_tr_f, y_tr_f)
    iso_f = IsotonicRegression(out_of_bounds="clip").fit(clf_f.predict_proba(X_ca_f)[:, 1], y_ca_f)
    raw_ca, raw_st = clf_f.predict_proba(X_ca_f)[:, 1], clf_f.predict_proba(X_st_f)[:, 1]
    cal_st = iso_f.predict(raw_st)

    rng_b = np.random.default_rng(99)
    real_frauds_X = X_st_f[y_st_f == 1]
    sampled_X = real_frauds_X[rng_b.choice(len(real_frauds_X), size=1000, replace=True)] + rng_b.normal(0, 0.35, size=(1000, 29))
    b_raw, b_cal = clf_f.predict_proba(sampled_X)[:, 1], iso_f.predict(clf_f.predict_proba(sampled_X)[:, 1])

    r_b, c_b, y_b = np.insert(raw_st, 65000, b_raw), np.insert(cal_st, 65000, b_cal), np.insert(y_st_f, 65000, np.ones(1000, dtype=int))
    print("\n2. SECOND INDEPENDENT BURST (1,000 JITTERED FRAUDS AT INDEX 65,000; TOTAL FRAUDS=1,131):")
    for mode in ["standard", "quarantine_guard_only"]:
        buf = list(raw_ca[-20000:])
        preds = np.zeros(len(r_b), dtype=int)
        for i, (rs, cp) in enumerate(zip(r_b, c_b)):
            fq = rs >= np.quantile(buf, 0.998)
            fg = cp >= 0.80
            preds[i] = int(fq or fg)
            if mode == "standard" or not fg:
                buf.append(rs); buf.pop(0)
        tp, al, fn = int(np.sum((preds == 1) & (y_b == 1))), int(np.sum(preds == 1)), int(np.sum(y_b == 1))
        print(f"  {mode:<22} -> Alerts={al} ({al/len(y_b)*100:.3f}%) | TP={tp}/{fn} | Recall={tp/fn*100:.1f}% | Precision={tp/al*100:.1f}%")
