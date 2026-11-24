import warnings
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score
from sklearn.ensemble import IsolationForest
import xgboost as xgb
import lightgbm as lgb

warnings.filterwarnings("ignore")

tr_txn = pd.read_csv("data/ieee-cis/train_transaction.csv")
tr_id = pd.read_csv("data/ieee-cis/train_identity.csv")
df = tr_txn.merge(tr_id, on="TransactionID", how="left").sort_values("TransactionDT").reset_index(drop=True)
del tr_txn, tr_id
df = df.drop_duplicates(subset=[c for c in df.columns if c != "TransactionID"]).reset_index(drop=True)
N = len(df)

drop_cols = {"TransactionID", "TransactionDT", "isFraud"}
static_cols = [c for c in df.columns if c not in drop_cols]
for c in static_cols:
    if df[c].dtype == "object" or str(df[c].dtype) == "str":
        df[c] = df[c].astype("category")
    elif df[c].dtype == "float64":
        df[c] = df[c].astype("float32")
num_cols = [c for c in static_cols if str(df[c].dtype) != "category"]

# 1. Paired Block-Bootstrap CI: LightGBM - XGBoost on 3 Disjoint OOT Windows
cuts = [0.60, 0.73, 0.86, 1.00]
y_all, p_xgb, p_lgb = [], [], []
for i in range(3):
    t_end, te_end = int(cuts[i] * N), int(cuts[i + 1] * N)
    c_start = int((cuts[i] - 0.10) * N)
    tr, ca, te = df.iloc[:c_start], df.iloc[c_start:t_end], df.iloc[t_end:te_end]
    y_tr, y_ca = tr["isFraud"].values, ca["isFraud"].values
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)

    mx = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                           colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
                           tree_method="hist", device="cpu", enable_categorical=True,
                           eval_metric="logloss", random_state=42, n_jobs=-1)
    mx.fit(tr[static_cols], y_tr)
    ix = IsotonicRegression(out_of_bounds="clip").fit(mx.predict_proba(ca[static_cols])[:, 1], y_ca)
    p_xgb.append(ix.predict(mx.predict_proba(te[static_cols])[:, 1]))

    ml = lgb.LGBMClassifier(n_estimators=300, num_leaves=63, learning_rate=0.05, subsample=0.8,
                            colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
                            random_state=42, n_jobs=-1, verbose=-1)
    ml.fit(tr[static_cols], y_tr)
    il = IsotonicRegression(out_of_bounds="clip").fit(ml.predict_proba(ca[static_cols])[:, 1], y_ca)
    p_lgb.append(il.predict(ml.predict_proba(te[static_cols])[:, 1]))
    y_all.append(te["isFraud"].values)

y_all, p_xgb, p_lgb = np.concatenate(y_all), np.concatenate(p_xgb), np.concatenate(p_lgb)
rng = np.random.default_rng(42)
bs_size, n_blocks = 3500, len(y_all) // 3500
deltas = []
for _ in range(500):
    idx = np.concatenate([np.arange(k * bs_size, (k + 1) * bs_size) for k in rng.integers(0, n_blocks, size=n_blocks)])
    if y_all[idx].sum() == 0:
        continue
    deltas.append(average_precision_score(y_all[idx], p_lgb[idx]) - average_precision_score(y_all[idx], p_xgb[idx]))
lo, hi = np.percentile(deltas, [2.5, 97.5])
print(f"=== 1. PAIRED CI (LightGBM - XGBoost) ===")
print(f"Delta PR-AUC: {average_precision_score(y_all, p_lgb) - average_precision_score(y_all, p_xgb):+.4f} [95% CI: {lo:+.4f}, {hi:+.4f}]")

# 2. Exact Alert Counts & Equal-Volume Comparison on ProductCD='C'
split_tr = int(0.60 * N)
tr_ab, te_ab = df.iloc[:int(0.50 * N)], df.iloc[split_tr:]
spw_ab = (tr_ab["isFraud"] == 0).sum() / max((tr_ab["isFraud"] == 1).sum(), 1)
is_c_te = (te_ab["ProductCD"].values == "C")
te_c = te_ab[is_c_te]
n_c_te = len(te_c)
n_c_fraud = int(te_c["isFraud"].sum())

m_ctrl = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                           colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw_ab,
                           tree_method="hist", device="cpu", enable_categorical=True,
                           eval_metric="logloss", random_state=42, n_jobs=-1)
m_ctrl.fit(tr_ab[static_cols], tr_ab["isFraud"].values)
p_ctrl_all = m_ctrl.predict_proba(te_ab[static_cols])[:, 1]
k_all = int(0.05 * len(te_ab))
flag_ctrl_all = p_ctrl_all >= np.sort(p_ctrl_all)[::-1][k_all - 1]
ctrl_c_alerts = int(flag_ctrl_all[is_c_te].sum())
ctrl_c_tp = int((flag_ctrl_all[is_c_te] & (te_c["isFraud"].values == 1)).sum())

# Equal-volume 5% of channel C (k_c) for both Control and Isolation Forest
k_c = int(0.05 * n_c_te)
p_ctrl_c = p_ctrl_all[is_c_te]
flag_ctrl_kc = p_ctrl_c >= np.sort(p_ctrl_c)[::-1][k_c - 1]
ctrl_kc_tp = int((flag_ctrl_kc & (te_c["isFraud"].values == 1)).sum())

tr_c_legit = df.iloc[:split_tr]
tr_c_legit = tr_c_legit[(tr_c_legit["ProductCD"] == "C") & (tr_c_legit["isFraud"] == 0)]
med_c = tr_c_legit[num_cols].median()
iso_f = IsolationForest(n_estimators=150, contamination=0.05, random_state=42, n_jobs=-1)
iso_f.fit(tr_c_legit[num_cols].fillna(med_c).values)
anom_scores = -iso_f.decision_function(te_c[num_cols].fillna(med_c).values)
flag_anom_kc = anom_scores >= np.sort(anom_scores)[::-1][k_c - 1]
anom_kc_tp = int((flag_anom_kc & (te_c["isFraud"].values == 1)).sum())

print(f"\n=== 2. ProductCD='C' CHANNEL TABLE (N_C={n_c_te:,}, Frauds={n_c_fraud:,}, 5% Channel Cap k_C={k_c:,}) ===")
print(f"Control (5% Global Budget)  : Alerts on C={ctrl_c_alerts:,} | TP={ctrl_c_tp:,} | Recall={ctrl_c_tp/n_c_fraud:.1%} | Prec={ctrl_c_tp/ctrl_c_alerts:.1%}")
print(f"Control (Equal 5% C Cap)    : Alerts on C={k_c:,} | TP={ctrl_kc_tp:,} | Recall={ctrl_kc_tp/n_c_fraud:.1%} | Prec={ctrl_kc_tp/k_c:.1%}")
print(f"Isolation Forest (5% C Cap) : Alerts on C={k_c:,} | TP={anom_kc_tp:,} | Recall={anom_kc_tp/n_c_fraud:.1%} | Prec={anom_kc_tp/k_c:.1%}")
print(f"Random Baseline (5% C Cap)  : Alerts on C={k_c:,} | Expected TP={int(0.05*n_c_fraud):,} | Recall=5.0% | Prec={n_c_fraud/n_c_te:.1%}")
