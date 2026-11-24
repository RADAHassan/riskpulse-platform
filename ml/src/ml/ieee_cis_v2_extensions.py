import time
import numpy as np
import pandas as pd
from collections import deque
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score
import xgboost as xgb

t0 = time.time()
tr_txn = pd.read_csv("data/ieee-cis/train_transaction.csv")
tr_id = pd.read_csv("data/ieee-cis/train_identity.csv")
df = tr_txn.merge(tr_id, on="TransactionID", how="left")
del tr_txn, tr_id

df = df.sort_values("TransactionDT").reset_index(drop=True)
df = df.drop_duplicates(subset=[c for c in df.columns if c != "TransactionID"]).reset_index(drop=True)
N = len(df)

# ==============================================================================
# 1. SHARPER CAUSAL ENTITY UID FEATURES: card1 + addr1 + D1_origin_day
# ==============================================================================
day = np.floor(df["TransactionDT"].values / 86400.0)
d1 = df["D1"].fillna(-999).values
origin_day = np.where(d1 >= 0, np.round(day - d1), -999).astype(int)

uid_str = (
    df["card1"].fillna(-1).astype(int).astype(str) + "_" +
    df["addr1"].fillna(-1).astype(int).astype(str) + "_" +
    pd.Series(origin_day).astype(str)
)
uid_codes = pd.Categorical(uid_str).codes

order = np.lexsort((df["TransactionDT"].values, uid_codes))
u_s = uid_codes[order]
a_s = df["TransactionAmt"].values[order]
t_s = df["TransactionDT"].values[order]

past_cnt = np.zeros(N, dtype=np.float32)
amt_ratio = np.ones(N, dtype=np.float32)
time_since = np.full(N, -1.0, dtype=np.float32)

change = np.flatnonzero(np.diff(u_s)) + 1
starts = np.concatenate(([0], change))
ends = np.concatenate((change, [N]))

for s, e in zip(starts, ends):
    if e - s <= 1:
        continue
    run_sum = 0.0
    for idx_pos, i in enumerate(range(s, e)):
        if idx_pos > 0:
            past_cnt[i] = idx_pos
            mean_past = run_sum / idx_pos
            amt_ratio[i] = a_s[i] / (mean_past + 1.0)
            time_since[i] = t_s[i] - t_s[i - 1]
        run_sum += a_s[i]

inv_order = np.empty(N, dtype=int)
inv_order[order] = np.arange(N)

uid_cols = ["uid_past_cnt", "uid_amt_to_mean_ratio", "uid_time_since_last"]
df["uid_past_cnt"] = past_cnt[inv_order]
df["uid_amt_to_mean_ratio"] = amt_ratio[inv_order]
df["uid_time_since_last"] = time_since[inv_order]

drop_cols = {"TransactionID", "TransactionDT", "isFraud"}
static_cols = [c for c in df.columns if c not in drop_cols and c not in uid_cols]
all_cols = static_cols + uid_cols

for c in all_cols:
    if df[c].dtype == "object" or str(df[c].dtype) == "str":
        df[c] = df[c].astype("category")
    elif df[c].dtype == "float64":
        df[c] = df[c].astype("float32")

# Disjoint OOT with sharper UID features
cuts = [0.60, 0.73, 0.86, 1.00]
oot_y, oot_p_cal = [], []

for i in range(3):
    t_end, te_end = int(cuts[i] * N), int(cuts[i + 1] * N)
    cal_start = int((cuts[i] - 0.10) * N)
    tr_df, ca_df, te_df = df.iloc[:cal_start], df.iloc[cal_start:t_end], df.iloc[t_end:te_end]

    y_tr = tr_df["isFraud"].values
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
        scale_pos_weight=spw, tree_method="hist", device="cpu",
        enable_categorical=True, eval_metric="logloss",
        random_state=42, n_jobs=-1
    )
    model.fit(tr_df[all_cols], y_tr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(
        model.predict_proba(ca_df[all_cols])[:, 1], ca_df["isFraud"].values
    )
    oot_y.append(te_df["isFraud"].values)
    oot_p_cal.append(iso.predict(model.predict_proba(te_df[all_cols])[:, 1]))

y_all = np.concatenate(oot_y)
p_all = np.concatenate(oot_p_cal)
pr_uid = average_precision_score(y_all, p_all)
print(f"\n=== 1. SHARPER CAUSAL ENTITY UID (card1+addr1+D1_origin) ===")
print(f"UID + Static Pooled OOT PR-AUC: {pr_uid:.4f} (vs. Static Baseline 0.4835)")

# ==============================================================================
# 2. NOVEL ATTACK TEST: HOLD OUT ProductCD == 'C' FRAUDS FROM TRAINING
# ==============================================================================
split_tr = int(0.60 * N)
tr_full = df.iloc[:split_tr]
te_full = df.iloc[split_tr:]

# Hold out all frauds from ProductCD == 'C' (cross-border / distinct channel)
tr_masked = tr_full[~((tr_full["isFraud"] == 1) & (tr_full["ProductCD"] == "C"))]
removed_n = len(tr_full) - len(tr_masked)

cal_cut = int(0.85 * len(tr_masked))
tr_sub, ca_sub = tr_masked.iloc[:cal_cut], tr_masked.iloc[cal_cut:]
spw_n = (tr_sub["isFraud"] == 0).sum() / max((tr_sub["isFraud"] == 1).sum(), 1)

m_nov = xgb.XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
    scale_pos_weight=spw_n, tree_method="hist", device="cpu",
    enable_categorical=True, eval_metric="logloss",
    random_state=42, n_jobs=-1
)
m_nov.fit(tr_sub[all_cols], tr_sub["isFraud"].values)
iso_nov = IsotonicRegression(out_of_bounds="clip").fit(
    m_nov.predict_proba(ca_sub[all_cols])[:, 1], ca_sub["isFraud"].values
)
p_nov = iso_nov.predict(m_nov.predict_proba(te_full[all_cols])[:, 1])

k_te = int(0.05 * len(te_full))  # 5% review budget
thresh_te = np.sort(p_nov)[::-1][k_te - 1]
flagged_te = (p_nov >= thresh_te)

is_fraud = (te_full["isFraud"].values == 1)
is_novel = (te_full["ProductCD"].values == "C")

seen_rec = flagged_te[is_fraud & ~is_novel].mean()
novel_rec = flagged_te[is_fraud & is_novel].mean()

print(f"\n=== 2. IEEE-CIS NOVEL ATTACK TEST (HELD-OUT ProductCD='C' FRAUDS) ===")
print(f"Removed {removed_n:,} ProductCD='C' frauds from training")
print(f"Seen-channel OOT Recall @ 5% Budget  : {seen_rec:.1%} ({flagged_te[is_fraud & ~is_novel].sum()}/{(is_fraud & ~is_novel).sum()})")
print(f"Novel-channel OOT Recall @ 5% Budget : {novel_rec:.1%} ({flagged_te[is_fraud & is_novel].sum()}/{(is_fraud & is_novel).sum()})")

# ==============================================================================
# 3. TWO-TIER STREAMING POLICY: AUTO-DECLINE (P>=0.80) + CAPPED HUMAN QUEUE (2%)
# ==============================================================================
def run_two_tier(p_stream, y_stream, W=20000, human_budget=0.02, auto_guard=0.80):
    buf = deque(maxlen=W)
    human_win = deque(maxlen=W)
    max_human = int(W * human_budget)
    human_in_win = 0
    auto_al, auto_tp, hum_al, hum_tp = 0, 0, 0, 0
    thresh = 0.50

    for i, (p, y) in enumerate(zip(p_stream, y_stream)):
        if len(buf) >= 1000 and i % 100 == 0:
            thresh = np.quantile(buf, 1.0 - human_budget)

        if p >= auto_guard:
            auto_al += 1
            if y == 1:
                auto_tp += 1
            # Do not pollute score buffer or human cap
            if len(human_win) == W:
                human_in_win -= human_win[0]
            human_win.append(0)
        else:
            wants_human = (p >= thresh)
            flagged_h = wants_human and (human_in_win < max_human)
            if len(human_win) == W:
                human_in_win -= human_win[0]
            human_win.append(1 if flagged_h else 0)
            human_in_win += (1 if flagged_h else 0)
            buf.append(p)
            if flagged_h:
                hum_al += 1
                if y == 1:
                    hum_tp += 1

    tot_tp = auto_tp + hum_tp
    tot_al = auto_al + hum_al
    print(f"Auto-Declines (P>=0.80): {auto_al:5d} ({auto_al/len(y_stream):.2%}) | Prec={auto_tp/max(auto_al,1):.1%}")
    print(f"Capped Human Queue (2%): {hum_al:5d} ({hum_al/len(y_stream):.2%}) | Prec={hum_tp/max(hum_al,1):.1%}")
    print(f"Combined Capture       : Recall={tot_tp/y_stream.sum():.1%} ({tot_tp}/{int(y_stream.sum())}) | Overall Prec={tot_tp/max(tot_al,1):.1%}")

print(f"\n=== 3. TWO-TIER STREAMING POLICY ON IEEE-CIS OOT ===")
run_two_tier(p_all, y_all)
print(f"\nTotal runtime: {time.time()-t0:.1f}s")
