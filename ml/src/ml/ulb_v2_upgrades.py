import os
import glob
import numpy as np
import pandas as pd
from collections import deque
from sklearn.isotonic import IsotonicRegression
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

# 1. Locate creditcard.csv
candidates = ["creditcard.csv", "data/creditcard.csv", "data/raw/creditcard.csv", "data-platform/creditcard.csv"]
csv_path = next((p for p in candidates if os.path.exists(p)), None)
if not csv_path:
    raise FileNotFoundError("Could not find creditcard.csv. Run from the directory containing it.")
print(f"Loaded dataset: {csv_path}")

df = pd.read_csv(csv_path).drop_duplicates().sort_values("Time").reset_index(drop=True)
features = ["Amount"] + [f"V{i}" for i in range(1, 29)]
N = len(df)

def fit_xgb_iso(train_df, cal_df, seed=42):
    X_tr, y_tr = train_df[features].values, train_df["Class"].values
    X_ca, y_ca = cal_df[features].values, cal_df["Class"].values
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
        scale_pos_weight=spw, eval_metric="logloss",
        random_state=seed, n_jobs=-1
    )
    model.fit(X_tr, y_tr)
    p_cal_raw = model.predict_proba(X_ca)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(p_cal_raw, y_ca)
    return model, iso

# 2. Disjoint OOT Windows: [60%, 73%], [73%, 86%], [86%, 100%]
cuts = [0.60, 0.73, 0.86, 1.00]
oot_y, oot_amt, oot_p_cal = [], [], []
oot_X_list = []

for i in range(3):
    t_end = int(cuts[i] * N)
    te_end = int(cuts[i + 1] * N)
    cal_start = int((cuts[i] - 0.10) * N)
    tr_df = df.iloc[:cal_start]
    ca_df = df.iloc[cal_start:t_end]
    te_df = df.iloc[t_end:te_end]

    model, iso = fit_xgb_iso(tr_df, ca_df, seed=42)
    p_raw = model.predict_proba(te_df[features].values)[:, 1]
    p_cal = iso.predict(p_raw)

    oot_y.append(te_df["Class"].values)
    oot_amt.append(te_df["Amount"].values)
    oot_p_cal.append(p_cal)
    oot_X_list.append(te_df[features].values)

y_all = np.concatenate(oot_y)
amt_all = np.concatenate(oot_amt)
p_all = np.concatenate(oot_p_cal)
X_all = np.vstack(oot_X_list)
budget_k = int(0.0020 * len(y_all))

# ==============================================================================
# UPGRADE 1: Expected-Loss Ranking vs. Probability Ranking @ 0.20% Budget
# ==============================================================================
def eval_ranking(scores, y, amt, k):
    top_idx = np.argsort(scores)[::-1][:k]
    tp = y[top_idx].sum()
    rec = tp / y.sum()
    prec = tp / k
    dol_rec = amt[top_idx][y[top_idx] == 1].sum() / amt[y == 1].sum()
    return tp, rec, prec, dol_rec

exp_loss = p_all * (amt_all + 25.0)
tp_p, rec_p, prec_p, dol_p = eval_ranking(p_all, y_all, amt_all, budget_k)
tp_e, rec_e, prec_e, dol_e = eval_ranking(exp_loss, y_all, amt_all, budget_k)

# Hourly block bootstrap (block_size=6000, B=1000) for Dollar Recall delta
rng = np.random.default_rng(42)
block_size = 6000
n_blocks = len(y_all) // block_size
deltas = []
for _ in range(1000):
    b_idx = rng.integers(0, n_blocks, size=n_blocks)
    idx = np.concatenate([np.arange(b * block_size, (b + 1) * block_size) for b in b_idx])
    yb, ab, pb, eb = y_all[idx], amt_all[idx], p_all[idx], exp_loss[idx]
    if yb.sum() == 0:
        continue
    kb = int(0.0020 * len(yb))
    _, _, _, dp = eval_ranking(pb, yb, ab, kb)
    _, _, _, de = eval_ranking(eb, yb, ab, kb)
    deltas.append(de - dp)

ci_lo, ci_hi = np.percentile(deltas, [2.5, 97.5])

print("\n=== UPGRADE 1: EXPECTED-LOSS RANKING (0.20% BUDGET) ===")
print(f"Probability Ranking   : TP={tp_p}/{y_all.sum()} | Recall={rec_p:.1%} | Prec={prec_p:.1%} | Dollar Recall={dol_p:.1%}")
print(f"Expected-Loss Ranking : TP={tp_e}/{y_all.sum()} | Recall={rec_e:.1%} | Prec={prec_e:.1%} | Dollar Recall={dol_e:.1%}")
print(f"Dollar Recall Delta   : {(dol_e - dol_p):+.1%} (95% Block-Bootstrap CI: [{ci_lo:+.1%}, {ci_hi:+.1%}])")

# ==============================================================================
# UPGRADE 2: Hard Per-Window Alert Cap on Normal, Burst 1 (+500), Burst 2 (+1000)
# ==============================================================================
def inject_burst(p_stream, y_stream, pos, n_inject, seed=42):
    r = np.random.default_rng(seed)
    fraud_scores = p_stream[y_stream == 1]
    jittered = np.clip(r.choice(fraud_scores, size=n_inject, replace=True) + r.normal(0, 0.02, size=n_inject), 0, 1)
    p_new = np.concatenate([p_stream[:pos], jittered, p_stream[pos:]])
    y_new = np.concatenate([y_stream[:pos], np.ones(n_inject, dtype=int), y_stream[pos:]])
    return p_new, y_new

def simulate_stream(p_stream, y_stream, W=20000, budget=0.0020, guard=0.80, hard_cap=False):
    buf = deque(maxlen=W)
    alert_window = deque(maxlen=W)  # tracks 1/0 for alerts in last W txns
    max_alerts = int(W * budget)    # 40 alerts per 20,000 txns
    alerts_in_win = 0
    total_alerts, tp = 0, 0

    # Warm-up threshold
    for i, (p, y) in enumerate(zip(p_stream, y_stream)):
        if len(buf) < 1000:
            thresh = 0.50
        elif i % 100 == 0:
            thresh = np.quantile(buf, 1.0 - budget)

        is_guard = (p >= guard)
        wants_alert = is_guard or (p >= thresh)

        if hard_cap and alerts_in_win >= max_alerts:
            flagged = False
        else:
            flagged = wants_alert

        # Update rolling alert cap window
        if len(alert_window) == W:
            alerts_in_win -= alert_window[0]
        alert_window.append(1 if flagged else 0)
        alerts_in_win += (1 if flagged else 0)

        # quarantine_guard_only: do not push guard alerts into score buffer
        if not is_guard:
            buf.append(p)

        if flagged:
            total_alerts += 1
            if y == 1:
                tp += 1

    rate = total_alerts / len(y_stream)
    rec = tp / y_stream.sum()
    prec = tp / max(total_alerts, 1)
    return total_alerts, rate, tp, int(y_stream.sum()), rec, prec

p_b1, y_b1 = inject_burst(p_all, y_all, pos=20000, n_inject=500, seed=42)
p_b2, y_b2 = inject_burst(p_all, y_all, pos=65000, n_inject=1000, seed=99)

print("\n=== UPGRADE 2: HARD PER-WINDOW ALERT CAP (W=20,000, MAX 40 ALERTS/WINDOW) ===")
for name, ps, ys in [("Normal OOT", p_all, y_all), ("Burst 1 (+500)", p_b1, y_b1), ("Burst 2 (+1000)", p_b2, y_b2)]:
    for cap_label, cap_flag in [("Uncapped", False), ("Hard Cap", True)]:
        al, rt, tp, tot, rc, pr = simulate_stream(ps, ys, hard_cap=cap_flag)
        print(f"{name:15s} | {cap_label:8s} | Alerts={al:4d} ({rt:.3%}) | Recall={rc:.1%} ({tp}/{tot}) | Prec={pr:.1%}")

# ==============================================================================
# UPGRADE 3: Novel Attack Test (Hold Out 1 Fraud Cluster from Training)
# ==============================================================================
split_tr = int(0.60 * N)
tr_full = df.iloc[:split_tr].copy()
te_full = df.iloc[split_tr:].copy()

v_cols = [f"V{i}" for i in range(1, 29)]
scaler = StandardScaler()
tr_frauds = tr_full[tr_full["Class"] == 1]
te_frauds = te_full[te_full["Class"] == 1]

km = KMeans(n_clusters=3, random_state=42, n_init=10)
tr_clusters = km.fit_predict(scaler.fit_transform(tr_frauds[v_cols]))
te_clusters = km.predict(scaler.transform(te_frauds[v_cols]))

# Hold out the smallest non-trivial cluster (>=15 test frauds if possible, else cluster 0)
counts_te = pd.Series(te_clusters).value_counts()
held_out_c = counts_te.index[1] if len(counts_te) > 1 else counts_te.index[0]

keep_mask = ~((tr_full["Class"] == 1) & (tr_full.index.isin(tr_frauds.index[tr_clusters == held_out_c])))
tr_masked = tr_full[keep_mask]

cal_cut = int(0.85 * len(tr_masked))
m_novel, iso_novel = fit_xgb_iso(tr_masked.iloc[:cal_cut], tr_masked.iloc[cal_cut:], seed=42)
p_novel = iso_novel.predict(m_novel.predict_proba(te_full[features].values)[:, 1])

k_te = int(0.0020 * len(te_full))
thresh_te = np.sort(p_novel)[::-1][k_te - 1]
flagged_te = (p_novel >= thresh_te)

te_fraud_mask = (te_full["Class"].values == 1)
flagged_frauds = flagged_te[te_fraud_mask]
novel_mask = (te_clusters == held_out_c)
seen_mask = ~novel_mask

print("\n=== UPGRADE 3: NOVEL ATTACK TEST (HELD-OUT FRAUD CLUSTER) ===")
print(f"Held-out cluster ID: {held_out_c} (removed {(tr_clusters == held_out_c).sum()} frauds from train)")
print(f"Seen-cluster OOT Recall @ 0.20%  : {flagged_frauds[seen_mask].mean():.1%} ({flagged_frauds[seen_mask].sum()}/{seen_mask.sum()})")
print(f"Novel-cluster OOT Recall @ 0.20% : {flagged_frauds[novel_mask].mean():.1%} ({flagged_frauds[novel_mask].sum()}/{novel_mask.sum()})")
