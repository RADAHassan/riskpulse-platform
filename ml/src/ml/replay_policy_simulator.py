import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.preprocessing import RobustScaler
from sklearn.isotonic import IsotonicRegression
from src.models.autoencoder import AutoencoderFeatureExtractor


def engineer_31d(df_slice: pd.DataFrame, scaler=None, fit: bool = False):
    hour = (df_slice["Time"].values / 3600.0) % 24.0
    hour_sin = np.sin(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    hour_cos = np.cos(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
    v_mat = df_slice[[f"V{i}" for i in range(1, 29)]].values
    amt_raw = df_slice["Amount"].values

    if fit:
        scaler = RobustScaler()
        amt_scaled = scaler.fit_transform(amt_raw.reshape(-1, 1))
    else:
        amt_scaled = scaler.transform(amt_raw.reshape(-1, 1))

    return np.hstack([amt_scaled, v_mat, hour_sin, hour_cos]), df_slice["Class"].values.astype(int), amt_raw, scaler


def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    quantiles = np.linspace(0, 100, bins + 1)
    cuts = np.percentile(expected, quantiles)
    cuts[0], cuts[-1] = -np.inf, np.inf
    exp_cnt = np.histogram(expected, bins=cuts)[0] / len(expected)
    act_cnt = np.histogram(actual, bins=cuts)[0] / len(actual)
    exp_cnt = np.clip(exp_cnt, 1e-6, None)
    act_cnt = np.clip(act_cnt, 1e-6, None)
    return float(np.sum((act_cnt - exp_cnt) * np.log(act_cnt / exp_cnt)))


def simulate_stream_policy(raw_init, raw_stream, cal_stream, y_stream, W=5000, target_rate=0.002, use_guard=True, guard_prob=0.80):
    buf = list(raw_init[-W:]) if len(raw_init) >= W else list(raw_init)
    preds = np.zeros(len(raw_stream), dtype=int)
    guard_triggers = 0

    for i, (r_score, c_prob) in enumerate(zip(raw_stream, cal_stream)):
        tau_q = np.quantile(buf, 1.0 - target_rate)
        flag_q = r_score >= tau_q
        flag_g = use_guard and (c_prob >= guard_prob)
        if flag_g and not flag_q:
            guard_triggers += 1
        preds[i] = int(flag_q or flag_g)

        buf.append(r_score)
        if len(buf) > W:
            buf.pop(0)

    n_frauds = max(1, int(np.sum(y_stream)))
    tp = int(np.sum((preds == 1) & (y_stream == 1)))
    total_alerts = int(np.sum(preds == 1))
    return {
        "realized_rate": total_alerts / len(y_stream) * 100.0,
        "alerts": total_alerts,
        "recall": tp / n_frauds * 100.0,
        "precision": tp / max(1, total_alerts) * 100.0,
        "guard_saves": guard_triggers,
    }


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv")
    if not csv_path.exists():
        csv_path = next(Path(".").rglob("creditcard.csv"))

    df_sorted = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True)
    n = len(df_sorted)

    # Fit on chronological Train (0-50%) & Calibrate on (50-60%), then replay full future stream (60-100%, 113,923 txns)
    X_tr, y_tr, _, sc = engineer_31d(df_sorted.iloc[: int(0.50 * n)], fit=True)
    X_ca, y_ca, _, _ = engineer_31d(df_sorted.iloc[int(0.50 * n) : int(0.60 * n)], scaler=sc, fit=False)
    X_st, y_st, _, _ = engineer_31d(df_sorted.iloc[int(0.60 * n) :], scaler=sc, fit=False)

    spw = float(np.sum(y_tr == 0) / np.sum(y_tr == 1))
    clf = xgb.XGBClassifier(
        n_estimators=213, max_depth=5, learning_rate=0.0955,
        colsample_bytree=0.7272, scale_pos_weight=spw,
        eval_metric="logloss", random_state=42, n_jobs=-1
    ).fit(X_tr, y_tr)

    iso = IsotonicRegression(out_of_bounds="clip").fit(clf.predict_proba(X_ca)[:, 1], y_ca)

    # Out-of-band Autoencoder drift monitor
    ae = AutoencoderFeatureExtractor(bottleneck_dim=8, epochs=12, batch_size=512, lr=1e-3).fit(X_tr[y_tr == 0])
    ae_mse_ca = ae.transform(X_ca)[:, 0]
    ae_mse_st = ae.transform(X_st)[:, 0]

    raw_ca = clf.predict_proba(X_ca)[:, 1]
    raw_st = clf.predict_proba(X_st)[:, 1]
    cal_st = iso.predict(raw_st)

    print("=======================================================================================")
    print("1. LIVE-STREAM REPLAY (60%->100%, N=113,923 TXNS): BUFFER SIZE W IN {1k, 5k, 20k}")
    print("=======================================================================================")
    for W in [1000, 5000, 20000]:
        res = simulate_stream_policy(raw_ca, raw_st, cal_st, y_st, W=W, target_rate=0.002, use_guard=True)
        print(
            f"  W={W:<6} | Realized Rate: {res['realized_rate']:.3f}% ({res['alerts']} alerts) | "
            f"Recall: {res['recall']:.1f}% | Precision: {res['precision']:.1f}% | Guard Extra Captures: {res['guard_saves']}"
        )

    print("\n=======================================================================================")
    print("2. SYNTHETIC COORDINATED FRAUD BURST TEST (80 HIGH-RISK FRAUDS INJECTED IN 500 TXNS)")
    print("=======================================================================================")
    fraud_pool_idx = np.where(y_st == 1)[0]
    burst_idx = np.random.default_rng(42).choice(fraud_pool_idx, size=80, replace=True)
    # Inject burst at step 20,000 of the stream
    raw_burst = np.insert(raw_st, 20000, raw_st[burst_idx])
    cal_burst = np.insert(cal_st, 20000, cal_st[burst_idx])
    y_burst = np.insert(y_st, 20000, y_st[burst_idx])

    res_no_guard = simulate_stream_policy(raw_ca, raw_burst, cal_burst, y_burst, W=1000, target_rate=0.002, use_guard=False)
    res_with_guard = simulate_stream_policy(raw_ca, raw_burst, cal_burst, y_burst, W=1000, target_rate=0.002, use_guard=True, guard_prob=0.80)
    print(f"  Rolling-1k ONLY (No Guard)    -> Recall: {res_no_guard['recall']:.1f}% | Alerts: {res_no_guard['alerts']}")
    print(f"  Rolling-1k + P>=0.80 Guard    -> Recall: {res_with_guard['recall']:.1f}% | Alerts: {res_with_guard['alerts']} (+{res_with_guard['guard_saves']} burst rescues)")

    print("\n=======================================================================================")
    print("3. SLIDING-WINDOW OUT-OF-BAND DRIFT TELEMETRY (AE_RECON_MSE PSI EVERY 20,000 TXNS)")
    print("=======================================================================================")
    for start in range(0, len(ae_mse_st), 20000):
        chunk = ae_mse_st[start : start + 20000]
        if len(chunk) < 5000:
            continue
        psi_val = compute_psi(ae_mse_ca, chunk)
        status = "ALERT (>0.25) -> TRIGGER RECALIBRATION" if psi_val > 0.25 else "NOMINAL"
        print(f"  Stream Txns [{start:>6}..{start+len(chunk):>6}] | AE_Recon_MSE PSI: {psi_val:.4f} | {status}")
