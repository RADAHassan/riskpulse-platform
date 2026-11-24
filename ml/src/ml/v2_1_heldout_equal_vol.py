import warnings
import numpy as np
import pandas as pd
import xgboost as xgb

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

split_tr = int(0.60 * N)
tr_full, te_ab = df.iloc[:int(0.50 * N)], df.iloc[split_tr:]
# Hold out all ProductCD == 'C' frauds from training
tr_masked = tr_full[~((tr_full["isFraud"] == 1) & (tr_full["ProductCD"] == "C"))]
spw = (tr_masked["isFraud"] == 0).sum() / max((tr_masked["isFraud"] == 1).sum(), 1)

m_held = xgb.XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
    colsample_bytree=0.8, reg_lambda=5.0, scale_pos_weight=spw,
    tree_method="hist", device="cpu", enable_categorical=True,
    eval_metric="logloss", random_state=42, n_jobs=-1
)
m_held.fit(tr_masked[static_cols], tr_masked["isFraud"].values)

te_c = te_ab[te_ab["ProductCD"].values == "C"]
n_c_te = len(te_c)
n_c_fraud = int(te_c["isFraud"].sum())
k_c = int(0.05 * n_c_te)  # 1,371 alerts

p_held_c = m_held.predict_proba(te_c[static_cols])[:, 1]
flag_held_kc = p_held_c >= np.sort(p_held_c)[::-1][k_c - 1]
held_kc_tp = int((flag_held_kc & (te_c["isFraud"].values == 1)).sum())

print(f"=== HELD-OUT SUPERVISED XGBOOST AT EQUAL 5% CHANNEL CAP (k_C={k_c:,}) ===")
print(f"Alerts on C={k_c:,} | TP={held_kc_tp:,} | Recall={held_kc_tp/n_c_fraud:.1%} | Prec={held_kc_tp/k_c:.1%}")
print(f"Max possible recall at k_C={k_c:,}: {k_c/n_c_fraud:.1%} ({k_c:,}/{n_c_fraud:,})")
