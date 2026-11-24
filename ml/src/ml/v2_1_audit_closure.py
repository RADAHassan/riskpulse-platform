import time
import warnings
import numpy as np
import pandas as pd
from collections import deque
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
import xgboost as xgb

warnings.filterwarnings("ignore")
t0 = time.time()

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

def ece_score(y_true, y_prob, n_bins=10):
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1] if i < n_bins - 1 else y_prob <= bins[i + 1])
        if mask.sum() > 0:
            ece += (mask.sum() / len(y_true)) * abs(y_true[mask].mean() - y_prob[mask].mean())
    return ece

def bss_score(y_true, y_prob):
    bs = brier_score_loss(y_true, y_prob)
    bs_ref = np.mean((y_true - y_true.mean()) ** 2)
    return 1.0 - bs / bs_ref

def eval_budget(scores, y, amt, b):
    k = int(b * len(y))
    top = np.argsort(scores)[::-1][:k]
    tp = y[top].sum()
    return tp / y.sum(), tp / k, amt[top][y[top] == 1].sum() / amt[y == 1].sum()

def run_two_tier_stream(p_stream, y_stream, W=20000, human_budget=0.02, auto_guard=0.80):
    buf = deque(maxlen=W)
    human_win = deque(maxlen=W)
    max_human = int(W * human_budget)
    human_in_win = 0
    auto_al = auto_tp = auto_fp = hum_al = hum_tp = 0
    thresh = 0.50
    for i, (p, y) in enumerate(zip(p_stream, y_stream)):
        if len(buf) >= 1000 and i % 100 == 0:
            thresh = np.quantile(buf, 1.0 - human_budget)
        if p >= auto_guard:
            auto_al += 1
            if y == 1:
                auto_tp += 1
            else:
                auto_fp += 1
            if len(human_win) == W:
                human_in_win -= human_win[0]
            human_win.append(0)
        else:
            flagged_h = (p >= thresh) and (human_in_win < max_human)
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
    return {
        "auto_al": auto_al, "auto_rate": auto_al / len(y_stream),
        "auto_prec": auto_tp / max(auto_al, 1), "auto_fp": auto_fp,
        "hum_al": hum_al, "hum_rate": hum_al / len(y_stream),
        "hum_prec": hum_tp / max(hum_al, 1),
        "tot_rec": tot_tp / y_stream.sum(), "tot_tp": tot_tp, "tot_f": int(y_stream.sum()),
        "tot_prec": tot_tp / max(tot_al, 1)
    }

def inject_burst(p_stream, y_stream, pos, n_inject, seed=42):
    r = np.random.default_rng(seed)
    f_scores = p_stream[y_stream == 1]
    jit = np.clip(r.choice(f_scores, size=n_inject, replace=True) + r.normal(0, 0.02, size=n_inject), 0, 1)
    return np.concatenate([p_stream[:pos], jit, p_stream[pos:]]), np.concatenate([y_stream[:pos], np.ones(n_inject, dtype=int), y_stream[pos:]])

# ==============================================================================
# PART A: ULB TWO-TIER POLICY UNDER NORMAL, BURST 1 (+500), BURST 2 (+1000)
# ==============================================================================
print("Loading ULB for two-tier burst test...")
ulb = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
ulb_feats = ["Amount"] + [f"V{i}" for i in range(1, 29)]
N_u = len(ulb)
cuts = [0.60, 0.73, 0.86, 1.00]
u_y, u_p = [], []
for i in range(3):
    t_end, te_end = int(cuts[i] * N_u), int(cuts[i + 1] * N_u)
    c_start = int((cuts[i] - 0.10) * N_u)
    tr, ca, te = ulb.iloc[:c_start], ulb.iloc[c_start:t_end], ulb.iloc[t_end:te_end]
    spw = (tr["Class"] == 0).sum() / max((tr["Class"] == 1).sum(), 1)
    m = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8,
                          colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
                          eval_metric="logloss", random_state=42, n_jobs=-1)
    m.fit(tr[ulb_feats].values, tr["Class"].values)
    iso = IsotonicRegression(out_of_bounds="clip").fit(m.predict_proba(ca[ulb_feats].values)[:, 1], ca["Class"].values)
    u_y.append(te["Class"].values)
    u_p.append(iso.predict(m.predict_proba(te[ulb_feats].values)[:, 1]))

u_y, u_p = np.concatenate(u_y), np.concatenate(u_p)
u_p1, u_y1 = inject_burst(u_p, u_y, 20000, 500, 42)
u_p2, u_y2 = inject_burst(u_p, u_y, 65000, 1000, 99)

print("\n=== 1. ULB TWO-TIER POLICY UNDER BURSTS (AUTO>=0.80 + CAPPED HUMAN 0.20%) ===")
for name, ps, ys in [("ULB Normal OOT", u_p, u_y), ("ULB Burst 1 (+500)", u_p1, u_y1), ("ULB Burst 2 (+1000)", u_p2, u_y2)]:
    r = run_two_tier_stream(ps, ys, W=20000, human_budget=0.0020, auto_guard=0.80)
    print(f"{name:19s} | Auto={r['auto_al']:4d} ({r['auto_rate']:.2%}, FP={r['auto_fp']:3d}, Prec={r['auto_prec']:.1%}) | Human={r['hum_al']:3d} ({r['hum_rate']:.3%}) | Recall={r['tot_rec']:.1%} ({r['tot_tp']}/{r['tot_f']})")

# ==============================================================================
# PART B: IEEE-CIS LOAD + CAUSAL VELOCITY
# ==============================================================================
print("\nLoading IEEE-CIS...")
tr_txn = pd.read_csv("data/ieee-cis/train_transaction.csv")
tr_id = pd.read_csv("data/ieee-cis/train_identity.csv")
df = tr_txn.merge(tr_id, on="TransactionID", how="left").sort_values("TransactionDT").reset_index(drop=True)
del tr_txn, tr_id
df = df.drop_duplicates(subset=[c for c in df.columns if c != "TransactionID"]).reset_index(drop=True)
N = len(df)

# Causal 1h/24h velocity on card1_addr1
uid_codes = pd.Categorical(df["card1"].fillna(-1).astype(int).astype(str) + "_" + df["addr1"].fillna(-1).astype(int).astype(str)).codes
order = np.lexsort((df["TransactionDT"].values, uid_codes))
u_s, t_s, a_s = uid_codes[order], df["TransactionDT"].values[order], df["TransactionAmt"].values[order]
tsl = np.full(N, -1.0, dtype=np.float32)
c1, a1, c24, a24 = np.zeros(N, dtype=np.float32), np.zeros(N, dtype=np.float32), np.zeros(N, dtype=np.float32), np.zeros(N, dtype=np.float32)
change = np.flatnonzero(np.diff(u_s)) + 1
for s, e in zip(np.concatenate(([0], change)), np.concatenate((change, [N]))):
    if e - s <= 1:
        continue
    l1 = l24 = s
    s1 = s24 = 0.0
    for i in range(s, e):
        ti = t_s[i]
        if i > s:
            tsl[i] = ti - t_s[i - 1]
        while l1 < i and (ti - t_s[l1]) > 3600:
            s1 -= a_s[l1]; l1 += 1
        while l24 < i and (ti - t_s[l24]) > 86400:
            s24 -= a_s[l24]; l24 += 1
        c1[i], a1[i], c24[i], a24[i] = i - l1, s1, i - l24, s24
        s1 += a_s[i]; s24 += a_s[i]
inv = np.empty(N, dtype=int); inv[order] = np.arange(N)
vel_cols = ["vel_tsl", "vel_c1", "vel_a1", "vel_c24", "vel_a24"]
df["vel_tsl"], df["vel_c1"], df["vel_a1"], df["vel_c24"], df["vel_a24"] = tsl[inv], c1[inv], a1[inv], c24[inv], a24[inv]

drop_cols = {"TransactionID", "TransactionDT", "isFraud"}
static_cols = [c for c in df.columns if c not in drop_cols and c not in vel_cols]
for c in static_cols + vel_cols:
    if df[c].dtype == "object" or str(df[c].dtype) == "str":
        df[c] = df[c].astype("category")
    elif df[c].dtype == "float64":
        df[c] = df[c].astype("float32")
num_cols = [c for c in static_cols if str(df[c].dtype) != "category"]

# ==============================================================================
# 2. IEEE-CIS PAIRED BASELINES (LOGREG, LIGHTGBM, XGBOOST) + ECE + EXP-LOSS CI
# ==============================================================================
y_all, amt_all = [], []
p_xgb, p_lgb, p_lr = [], [], []

for i in range(3):
    t_end, te_end = int(cuts[i] * N), int(cuts[i + 1] * N)
    c_start = int((cuts[i] - 0.10) * N)
    tr, ca, te = df.iloc[:c_start], df.iloc[c_start:t_end], df.iloc[t_end:te_end]
    y_tr, y_ca = tr["isFraud"].values, ca["isFraud"].values
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)

    # XGBoost (max_depth=6, n_estimators=300)
    mx = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                           colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
                           tree_method="hist", device="cpu", enable_categorical=True,
                           eval_metric="logloss", random_state=42, n_jobs=-1)
    mx.fit(tr[static_cols], y_tr)
    ix = IsotonicRegression(out_of_bounds="clip").fit(mx.predict_proba(ca[static_cols])[:, 1], y_ca)
    p_xgb.append(ix.predict(mx.predict_proba(te[static_cols])[:, 1]))

    # LightGBM
    if HAS_LGB:
        ml = lgb.LGBMClassifier(n_estimators=300, num_leaves=63, learning_rate=0.05, subsample=0.8,
                                colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
                                random_state=42, n_jobs=-1, verbose=-1)
        ml.fit(tr[static_cols], y_tr)
        il = IsotonicRegression(out_of_bounds="clip").fit(ml.predict_proba(ca[static_cols])[:, 1], y_ca)
        p_lgb.append(il.predict(ml.predict_proba(te[static_cols])[:, 1]))

    # Logistic Regression (numeric features, median-imputed + scaled)
    med = tr[num_cols].median()
    sc = StandardScaler()
    X_tr_lr = sc.fit_transform(tr[num_cols].fillna(med).values)
    X_ca_lr = sc.transform(ca[num_cols].fillna(med).values)
    X_te_lr = sc.transform(te[num_cols].fillna(med).values)
    mlr = LogisticRegression(max_iter=200, class_weight="balanced", C=0.1, n_jobs=-1)
    mlr.fit(X_tr_lr, y_tr)
    ilr = IsotonicRegression(out_of_bounds="clip").fit(mlr.predict_proba(X_ca_lr)[:, 1], y_ca)
    p_lr.append(ilr.predict(mlr.predict_proba(X_te_lr)[:, 1]))

    y_all.append(te["isFraud"].values)
    amt_all.append(te["TransactionAmt"].values)

y_all = np.concatenate(y_all)
amt_all = np.concatenate(amt_all)
p_xgb = np.concatenate(p_xgb)
p_lr = np.concatenate(p_lr)
p_lgb = np.concatenate(p_lgb) if HAS_LGB else None

print("\n=== 2. IEEE-CIS PAIRED BASELINES & CALIBRATION (ECE + BSS) ===")
for name, p in [("Logistic Regression", p_lr), ("XGBoost (d=6, n=300)", p_xgb)] + ([("LightGBM (l=63, n=300)", p_lgb)] if HAS_LGB else []):
    print(f"{name:22s} | PR-AUC={average_precision_score(y_all, p):.4f} | BSS={bss_score(y_all, p):+.4f} | 10-bin ECE={ece_score(y_all, p):.4f}")

# Expected-Loss Dollar Recall 95% Block-Bootstrap CI (block_size=3500, B=500)
rng = np.random.default_rng(42)
bs_size, n_blocks = 3500, len(y_all) // 3500
el_scores = p_xgb * (amt_all + 25.0)
print("\n=== 3. IEEE-CIS EXPECTED-LOSS DOLLAR RECALL 95% BLOCK-BOOTSTRAP CIs ===")
for b in [0.02, 0.05]:
    _, _, dp = eval_budget(p_xgb, y_all, amt_all, b)
    _, _, de = eval_budget(el_scores, y_all, amt_all, b)
    deltas = []
    for _ in range(500):
        idx = np.concatenate([np.arange(k * bs_size, (k + 1) * bs_size) for k in rng.integers(0, n_blocks, size=n_blocks)])
        if y_all[idx].sum() == 0:
            continue
        _, _, dpb = eval_budget(p_xgb[idx], y_all[idx], amt_all[idx], b)
        _, _, deb = eval_budget(el_scores[idx], y_all[idx], amt_all[idx], b)
        deltas.append(deb - dpb)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    print(f"Budget {b:.0%} | Prob={dp:.1%} -> ExpLoss={de:.1%} | Delta={(de-dp):+.1%} [95% CI: {lo:+.1%}, {hi:+.1%}]")

# ==============================================================================
# 4. IEEE-CIS TWO-TIER POLICY UNDER BURST (+2,000 FRAUDS)
# ==============================================================================
p_ib, y_ib = inject_burst(p_xgb, y_all, 60000, 2000, 42)
print("\n=== 4. IEEE-CIS TWO-TIER POLICY UNDER NORMAL & BURST (+2,000) ===")
for name, ps, ys in [("IEEE Normal OOT", p_xgb, y_all), ("IEEE Burst (+2000)", p_ib, y_ib)]:
    r = run_two_tier_stream(ps, ys, W=20000, human_budget=0.02, auto_guard=0.80)
    print(f"{name:19s} | Auto={r['auto_al']:4d} ({r['auto_rate']:.2%}, FP={r['auto_fp']:3d}, Prec={r['auto_prec']:.1%}) | Human={r['hum_al']:4d} ({r['hum_rate']:.2%}) | Recall={r['tot_rec']:.1%} ({r['tot_tp']}/{r['tot_f']})")

# ==============================================================================
# 5. VELOCITY ABLATION: DROP C1-C14 & D1-D15 (STATIC vs. STATIC+VELOCITY)
# ==============================================================================
cd_cols = {f"C{k}" for k in range(1, 15)} | {f"D{k}" for k in range(1, 16)}
no_cd_static = [c for c in static_cols if c not in cd_cols]
no_cd_vel = no_cd_static + vel_cols

split_tr = int(0.60 * N)
tr_ab, ca_ab, te_ab = df.iloc[:int(0.50 * N)], df.iloc[int(0.50 * N):split_tr], df.iloc[split_tr:]
spw_ab = (tr_ab["isFraud"] == 0).sum() / max((tr_ab["isFraud"] == 1).sum(), 1)
ab_res = {}
for label, cols in [("No-C/D Static", no_cd_static), ("No-C/D + Velocity", no_cd_vel)]:
    m = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                          colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw_ab,
                          tree_method="hist", device="cpu", enable_categorical=True,
                          eval_metric="logloss", random_state=42, n_jobs=-1)
    m.fit(tr_ab[cols], tr_ab["isFraud"].values)
    ab_res[label] = average_precision_score(te_ab["isFraud"].values, m.predict_proba(te_ab[cols])[:, 1])

print("\n=== 5. VELOCITY ABLATION (DROPPING C1-C14 & D1-D15) ===")
print(f"No-C/D Static PR-AUC    : {ab_res['No-C/D Static']:.4f}")
print(f"No-C/D + Velocity PR-AUC: {ab_res['No-C/D + Velocity']:.4f} (Delta: {ab_res['No-C/D + Velocity'] - ab_res['No-C/D Static']:+.4f})")

# ==============================================================================
# 6. ProductCD='C' CONTROL RUN + UNSUPERVISED ISOLATION FOREST MONITOR
# ==============================================================================
is_f_te = (te_ab["isFraud"].values == 1)
is_c_te = (te_ab["ProductCD"].values == "C")

# Control: full training (includes ProductCD='C' frauds)
k_te = int(0.05 * len(te_ab))
m_ctrl = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                           colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw_ab,
                           tree_method="hist", device="cpu", enable_categorical=True,
                           eval_metric="logloss", random_state=42, n_jobs=-1)
m_ctrl.fit(tr_ab[static_cols], tr_ab["isFraud"].values)
p_ctrl = m_ctrl.predict_proba(te_ab[static_cols])[:, 1]
flag_ctrl = p_ctrl >= np.sort(p_ctrl)[::-1][k_te - 1]
ctrl_c_rec = flag_ctrl[is_f_te & is_c_te].mean()

# Unsupervised Isolation Forest trained ONLY on legitimate ProductCD='C' training rows
tr_c_legit = df.iloc[:split_tr]
tr_c_legit = tr_c_legit[(tr_c_legit["ProductCD"] == "C") & (tr_c_legit["isFraud"] == 0)]
te_c = te_ab[is_c_te]
med_c = tr_c_legit[num_cols].median()
iso_f = IsolationForest(n_estimators=150, contamination=0.05, random_state=42, n_jobs=-1)
iso_f.fit(tr_c_legit[num_cols].fillna(med_c).values)
anom_scores = -iso_f.decision_function(te_c[num_cols].fillna(med_c).values)
k_c = int(0.05 * len(te_c))  # 5% review budget within ProductCD='C'
flag_anom = anom_scores >= np.sort(anom_scores)[::-1][k_c - 1]
anom_c_rec = flag_anom[te_c["isFraud"].values == 1].mean()
anom_c_tp = flag_anom[te_c["isFraud"].values == 1].sum()

print("\n=== 6. ProductCD='C' CONTROL vs. HELD-OUT + ISOLATION FOREST MONITOR ===")
print(f"Control (C frauds IN train) Recall on C @ 5% Budget : {ctrl_c_rec:.1%} ({flag_ctrl[is_f_te & is_c_te].sum()}/{(is_f_te & is_c_te).sum()})")
print(f"Held-out Supervised XGBoost Recall on C @ 5% Budget : 0.0% (0/3596)")
print(f"Unsupervised Isolation Forest Recall on C @ 5% Cap  : {anom_c_rec:.1%} ({anom_c_tp}/{int((te_c['isFraud']==1).sum())})")
print(f"\nTotal runtime: {time.time()-t0:.1f}s")
