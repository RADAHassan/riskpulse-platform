import time
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss
import xgboost as xgb

t0 = time.time()
print("Loading IEEE-CIS transaction + identity tables...")
tr_txn = pd.read_csv("data/ieee-cis/train_transaction.csv")
tr_id = pd.read_csv("data/ieee-cis/train_identity.csv")
df = tr_txn.merge(tr_id, on="TransactionID", how="left")
del tr_txn, tr_id

# Sort strictly chronologically and drop exact feature duplicates
df = df.sort_values("TransactionDT").reset_index(drop=True)
before_n = len(df)
df = df.drop_duplicates(subset=[c for c in df.columns if c != "TransactionID"]).reset_index(drop=True)
print(f"Loaded {len(df):,} rows (dropped {before_n - len(df):,} duplicates) | Frauds: {df['isFraud'].sum():,} ({df['isFraud'].mean():.2%}) | {time.time()-t0:.1f}s")

# ==============================================================================
# STRICTLY CAUSAL ENTITY & VELOCITY FEATURES (1h, 24h, time-since-last)
# ==============================================================================
t_vel = time.time()
uid_str = df["card1"].fillna(-1).astype(int).astype(str) + "_" + df["addr1"].fillna(-1).astype(int).astype(str)
uid_codes = pd.Categorical(uid_str).codes

# Sort by (uid_codes, TransactionDT) while preserving original chronological index
orig_idx = np.arange(len(df))
order = np.lexsort((df["TransactionDT"].values, uid_codes))
u_s = uid_codes[order]
t_s = df["TransactionDT"].values[order]
a_s = df["TransactionAmt"].values[order]

n = len(df)
time_since = np.full(n, -1.0, dtype=np.float32)
cnt_1h = np.zeros(n, dtype=np.float32)
amt_1h = np.zeros(n, dtype=np.float32)
cnt_24h = np.zeros(n, dtype=np.float32)
amt_24h = np.zeros(n, dtype=np.float32)

# Find group boundaries
change = np.flatnonzero(np.diff(u_s)) + 1
starts = np.concatenate(([0], change))
ends = np.concatenate((change, [n]))

for s, e in zip(starts, ends):
    if e - s <= 1:
        continue
    l1 = s
    l24 = s
    sum1 = 0.0
    sum24 = 0.0
    for i in range(s, e):
        ti = t_s[i]
        if i > s:
            time_since[i] = ti - t_s[i - 1]
        # Evict transactions older than 1h (3600s) and 24h (86400s)
        while l1 < i and (ti - t_s[l1]) > 3600:
            sum1 -= a_s[l1]
            l1 += 1
        while l24 < i and (ti - t_s[l24]) > 86400:
            sum24 -= a_s[l24]
            l24 += 1
        # Strictly causal: excludes index i itself
        cnt_1h[i] = i - l1
        amt_1h[i] = sum1
        cnt_24h[i] = i - l24
        amt_24h[i] = sum24
        # Add index i for subsequent transactions
        sum1 += a_s[i]
        sum24 += a_s[i]

# Map back to original chronological order
inv_order = np.empty(n, dtype=int)
inv_order[order] = np.arange(n)

vel_cols = ["vel_time_since_last", "vel_cnt_1h", "vel_amt_1h", "vel_cnt_24h", "vel_amt_24h"]
df["vel_time_since_last"] = time_since[inv_order]
df["vel_cnt_1h"] = cnt_1h[inv_order]
df["vel_amt_1h"] = amt_1h[inv_order]
df["vel_cnt_24h"] = cnt_24h[inv_order]
df["vel_amt_24h"] = amt_24h[inv_order]
print(f"Engineered 5 strictly causal velocity features in {time.time()-t_vel:.1f}s")

# Prepare feature types (float32 + pandas category for native XGBoost handling)
drop_cols = {"TransactionID", "TransactionDT", "isFraud"}
static_cols = [c for c in df.columns if c not in drop_cols and c not in vel_cols]
all_cols = static_cols + vel_cols

for c in all_cols:
    if df[c].dtype == "object" or str(df[c].dtype) == "str":
        df[c] = df[c].astype("category")
    elif df[c].dtype == "float64":
        df[c] = df[c].astype("float32")

# Detect GPU availability for XGBoost
device = "cuda"
try:
    _m = xgb.XGBClassifier(n_estimators=2, tree_method="hist", device="cuda")
    _m.fit(np.zeros((10, 2)), np.array([0, 1] * 5))
    print("XGBoost device: CUDA (GPU)")
except Exception:
    device = "cpu"
    print("XGBoost device: CPU")

# ==============================================================================
# DISJOINT OOT EVALUATION: STATIC BASELINE vs. STATIC + CAUSAL VELOCITY
# ==============================================================================
cuts = [0.60, 0.73, 0.86, 1.00]
N = len(df)

def run_oot(feature_cols, label):
    t_start = time.time()
    oot_y, oot_amt, oot_p_raw, oot_p_cal = [], [], [], []
    for i in range(3):
        t_end = int(cuts[i] * N)
        te_end = int(cuts[i + 1] * N)
        cal_start = int((cuts[i] - 0.10) * N)

        tr_df = df.iloc[:cal_start]
        ca_df = df.iloc[cal_start:t_end]
        te_df = df.iloc[t_end:te_end]

        y_tr = tr_df["isFraud"].values
        y_ca = ca_df["isFraud"].values
        spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)

        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
            scale_pos_weight=spw, tree_method="hist", device=device,
            enable_categorical=True, eval_metric="logloss",
            random_state=42, n_jobs=-1
        )
        model.fit(tr_df[feature_cols], y_tr)
        p_ca_raw = model.predict_proba(ca_df[feature_cols])[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_ca_raw, y_ca)

        p_te_raw = model.predict_proba(te_df[feature_cols])[:, 1]
        p_te_cal = iso.predict(p_te_raw)

        oot_y.append(te_df["isFraud"].values)
        oot_amt.append(te_df["TransactionAmt"].values)
        oot_p_raw.append(p_te_raw)
        oot_p_cal.append(p_te_cal)

    y = np.concatenate(oot_y)
    amt = np.concatenate(oot_amt)
    p_raw = np.concatenate(oot_p_raw)
    p_cal = np.concatenate(oot_p_cal)
    print(f"Finished {label} (3 disjoint OOT windows) in {time.time()-t_start:.1f}s")
    return y, amt, p_raw, p_cal

y_all, amt_all, p_raw_stat, p_cal_stat = run_oot(static_cols, "Static Baseline")
_, _, p_raw_vel, p_cal_vel = run_oot(all_cols, "Static + Causal Velocity")

# ==============================================================================
# METRICS & DAILY BLOCK-BOOTSTRAP CIs (block_size=3,500, B=500)
# ==============================================================================
def bss(y, p):
    bs = brier_score_loss(y, p)
    bs_ref = np.mean((y - y.mean()) ** 2)
    return 1.0 - bs / bs_ref

def eval_budget(scores, y, amt, budget_frac):
    k = int(budget_frac * len(y))
    top = np.argsort(scores)[::-1][:k]
    tp = y[top].sum()
    rec = tp / y.sum()
    prec = tp / k
    dol = amt[top][y[top] == 1].sum() / amt[y == 1].sum()
    return rec, prec, dol

pr_stat = average_precision_score(y_all, p_cal_stat)
pr_vel = average_precision_score(y_all, p_cal_vel)

rng = np.random.default_rng(42)
block_size = 3500
n_blocks = len(y_all) // block_size
bs_stat, bs_vel, bs_delta = [], [], []

for _ in range(500):
    b_idx = rng.integers(0, n_blocks, size=n_blocks)
    idx = np.concatenate([np.arange(b * block_size, (b + 1) * block_size) for b in b_idx])
    yb = y_all[idx]
    if yb.sum() == 0:
        continue
    ps = average_precision_score(yb, p_cal_stat[idx])
    pv = average_precision_score(yb, p_cal_vel[idx])
    bs_stat.append(ps)
    bs_vel.append(pv)
    bs_delta.append(pv - ps)

s_lo, s_hi = np.percentile(bs_stat, [2.5, 97.5])
v_lo, v_hi = np.percentile(bs_vel, [2.5, 97.5])
d_lo, d_hi = np.percentile(bs_delta, [2.5, 97.5])

print("\n=== IEEE-CIS DISJOINT OOT SUMMARY (POOLED N={:,}, FRAUDS={:,}) ===".format(len(y_all), int(y_all.sum())))
print(f"Static Baseline PR-AUC          : {pr_stat:.4f} [95% CI: {s_lo:.4f}, {s_hi:.4f}]")
print(f"Static + Causal Velocity PR-AUC : {pr_vel:.4f} [95% CI: {v_lo:.4f}, {v_hi:.4f}]")
print(f"Delta PR-AUC (Velocity - Static): {(pr_vel - pr_stat):+.4f} [95% CI: {d_lo:+.4f}, {d_hi:+.4f}]")

print("\n=== CALIBRATION (BRIER SKILL SCORE) ===")
print(f"Static Raw BSS: {bss(y_all, p_raw_stat):+.4f} -> Isotonic BSS: {bss(y_all, p_cal_stat):+.4f}")
print(f"Veloc. Raw BSS: {bss(y_all, p_raw_vel):+.4f} -> Isotonic BSS: {bss(y_all, p_cal_vel):+.4f}")

print("\n=== FIXED-CAPACITY OPERATING POINTS (VELOCITY MODEL) ===")
for b in [0.02, 0.05]:
    r_p, pr_p, d_p = eval_budget(p_cal_vel, y_all, amt_all, b)
    r_e, pr_e, d_e = eval_budget(p_cal_vel * (amt_all + 25.0), y_all, amt_all, b)
    print(f"Budget {b:.0%} | Prob Ranking     : Recall={r_p:.1%} | Prec={pr_p:.1%} | Dollar Recall={d_p:.1%}")
    print(f"Budget {b:.0%} | Exp-Loss Ranking : Recall={r_e:.1%} | Prec={pr_e:.1%} | Dollar Recall={d_e:.1%}")
