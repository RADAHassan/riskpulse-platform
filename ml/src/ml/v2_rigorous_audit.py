import warnings
import numpy as np
import pandas as pd
import optuna
import xgboost as xgb
import lightgbm as lgb
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression as PlattLR
from sklearn.metrics import average_precision_score, brier_score_loss

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)


def build_features(df_slice: pd.DataFrame, scaler=None, fit: bool = False, include_hour: bool = True):
    v_mat = df_slice[[f"V{i}" for i in range(1, 29)]].values
    amt_raw = df_slice["Amount"].values

    if fit:
        scaler = RobustScaler()
        amt_scaled = scaler.fit_transform(amt_raw.reshape(-1, 1))
    else:
        amt_scaled = scaler.transform(amt_raw.reshape(-1, 1))

    if include_hour:
        hour = (df_slice["Time"].values / 3600.0) % 24.0
        hour_sin = np.sin(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
        hour_cos = np.cos(2.0 * np.pi * hour / 24.0).reshape(-1, 1)
        X = np.hstack([amt_scaled, v_mat, hour_sin, hour_cos])
    else:
        X = np.hstack([amt_scaled, v_mat])

    y = df_slice["Class"].values.astype(int)
    return X, y, amt_raw, scaler


def brier_skill_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    b_model = brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))
    b_ref = brier_score_loss(y_true, np.full_like(y_prob, np.mean(y_true), dtype=float))
    return float(1.0 - (b_model / b_ref))


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1]) if i < n_bins - 1 else (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        if np.any(mask):
            ece += (np.sum(mask) / len(y_true)) * abs(np.mean(y_true[mask]) - np.mean(y_prob[mask]))
    return float(ece)


def recall_at_fpr(y_true: np.ndarray, scores: np.ndarray, target_fpr: float) -> float:
    neg_scores = scores[y_true == 0]
    thresh = np.quantile(neg_scores, 1.0 - target_fpr)
    return float(np.sum((scores >= thresh) & (y_true == 1)) / np.sum(y_true == 1) * 100.0)


def dollar_recall_at_rate(y_true: np.ndarray, scores: np.ndarray, amounts: np.ndarray, alert_rate: float = 0.002):
    k = max(1, int(len(y_true) * alert_rate))
    top_k = np.argsort(scores)[::-1][:k]
    pred = np.zeros(len(y_true), dtype=int)
    pred[top_k] = 1
    rec_cnt = np.sum((pred == 1) & (y_true == 1)) / np.sum(y_true == 1) * 100.0
    prec_cnt = np.sum((pred == 1) & (y_true == 1)) / k * 100.0
    rec_usd = np.sum(amounts[(pred == 1) & (y_true == 1)]) / np.sum(amounts[y_true == 1]) * 100.0
    return float(rec_cnt), float(prec_cnt), float(rec_usd)


def tune_xgb_temporal(df_train_block: pd.DataFrame, include_hour: bool = True, n_trials: int = 25):
    """Strict expanding-window chronological CV inside the pre-OOT training block."""
    n = len(df_train_block)
    splits = [(0.0, 0.50, 0.67), (0.0, 0.67, 0.84), (0.0, 0.84, 1.00)]
    fold_data = []
    for s0, s1, s2 in splits:
        Xtr, ytr, _, sc = build_features(df_train_block.iloc[int(s0 * n) : int(s1 * n)], fit=True, include_hour=include_hour)
        Xva, yva, _, _ = build_features(df_train_block.iloc[int(s1 * n) : int(s2 * n)], scaler=sc, fit=False, include_hour=include_hour)
        fold_data.append((Xtr, ytr, Xva, yva))

    def objective(trial):
        params = {
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
        for Xtr, ytr, Xva, yva in fold_data:
            spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
            clf = xgb.XGBClassifier(**params, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1)
            clf.fit(Xtr, ytr)
            aps.append(average_precision_score(yva, clf.predict_proba(Xva)[:, 1]))
        return float(np.mean(aps))

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)
    return study.best_params


if __name__ == "__main__":
    csv_path = Path("data/creditcard.csv")
    if not csv_path.exists():
        csv_path = next(Path(".").rglob("creditcard.csv"))

    df_raw = pd.read_csv(csv_path).sort_values("Time").reset_index(drop=True)
    feature_cols = [f"V{i}" for i in range(1, 29)] + ["Amount"]
    df_dedup = df_raw.drop_duplicates(subset=feature_cols, keep="first").reset_index(drop=True)
    print(f"1. DEDUPLICATION: {len(df_raw):,} -> {len(df_dedup):,} rows ({len(df_raw) - len(df_dedup):,} exact duplicates removed)")

    n = len(df_dedup)
    windows = [
        ("Window 1", 0.0, 0.50, 0.60, 0.73),
        ("Window 2", 0.0, 0.60, 0.73, 0.86),
        ("Window 3", 0.0, 0.70, 0.85, 1.00),
    ]

    # 2. Temporal Optuna Tuning strictly on pre-OOT block (first 60% of deduplicated stream)
    pre_oot_df = df_dedup.iloc[: int(0.60 * n)]
    best_params_29d = tune_xgb_temporal(pre_oot_df, include_hour=False, n_trials=25)
    best_params_31d = tune_xgb_temporal(pre_oot_df, include_hour=True, n_trials=25)
    print(f"2. TEMPORAL OPTUNA PARAMS (29D No-Hour): {best_params_29d}")

    models = [
        "1_LogReg_29D",
        "2_Default_XGB_29D",
        "3_LightGBM_29D",
        "4_TemporalTuned_XGB_29D (No Hour)",
        "5_TemporalTuned_XGB_31D (With Hour)",
    ]
    pooled_y, pooled_amt = [], []
    pooled_scores = {m: [] for m in models}
    cal_logs = {"none": [], "sigmoid_platt": [], "isotonic": []}

    for label, s0, s1, s2, s3 in windows:
        tr_df = df_dedup.iloc[int(s0 * n) : int(s1 * n)]
        ca_df = df_dedup.iloc[int(s1 * n) : int(s2 * n)]
        oo_df = df_dedup.iloc[int(s2 * n) : int(s3 * n)]

        Xtr29, ytr, _, sc29 = build_features(tr_df, fit=True, include_hour=False)
        Xca29, yca, _, _ = build_features(ca_df, scaler=sc29, fit=False, include_hour=False)
        Xoo29, yoo, amtoo, _ = build_features(oo_df, scaler=sc29, fit=False, include_hour=False)

        Xtr31, _, _, sc31 = build_features(tr_df, fit=True, include_hour=True)
        Xoo31, _, _, _ = build_features(oo_df, scaler=sc31, fit=False, include_hour=True)

        spw = float(np.sum(ytr == 0) / np.sum(ytr == 1))
        pooled_y.append(yoo)
        pooled_amt.append(amtoo)

        # Baselines (29D)
        std = StandardScaler().fit(Xtr29)
        lr = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42).fit(std.transform(Xtr29), ytr)
        pooled_scores["1_LogReg_29D"].append(lr.predict_proba(std.transform(Xoo29))[:, 1])

        def_xgb = xgb.XGBClassifier(scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr)
        pooled_scores["2_Default_XGB_29D"].append(def_xgb.predict_proba(Xoo29)[:, 1])

        lgbm = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1).fit(Xtr29, ytr)
        pooled_scores["3_LightGBM_29D"].append(lgbm.predict_proba(Xoo29)[:, 1])

        # Temporal-Tuned 29D (No Hour)
        t_xgb29 = xgb.XGBClassifier(**best_params_29d, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr29, ytr)
        raw_ca29 = t_xgb29.predict_proba(Xca29)[:, 1]
        raw_oo29 = t_xgb29.predict_proba(Xoo29)[:, 1]
        pooled_scores["4_TemporalTuned_XGB_29D (No Hour)"].append(raw_oo29)

        # Temporal-Tuned 31D (With Hour)
        t_xgb31 = xgb.XGBClassifier(**best_params_31d, scale_pos_weight=spw, eval_metric="logloss", random_state=42, n_jobs=-1).fit(Xtr31, ytr)
        pooled_scores["5_TemporalTuned_XGB_31D (With Hour)"].append(t_xgb31.predict_proba(Xoo31)[:, 1])

        # Calibration comparison on Temporal-Tuned 29D (Train on Train+Cal for uncalibrated, fit calibrators on Cal)
        cal_logs["none"].append((yoo, raw_oo29))

        platt = PlattLR().fit(raw_ca29.reshape(-1, 1), yca)
        p_sig = platt.predict_proba(raw_oo29.reshape(-1, 1))[:, 1]
        cal_logs["sigmoid_platt"].append((yoo, p_sig))

        iso = IsotonicRegression(out_of_bounds="clip").fit(raw_ca29, yca)
        p_iso = iso.predict(raw_oo29)
        cal_logs["isotonic"].append((yoo, p_iso))

    print("\n=========================================================================================================")
    print("3. POOLED DEDUPLICATED OOT BENCHMARK + 95% BOOTSTRAP CIs (PR-AUC, FPR RECALL, DOLLAR-WEIGHTED RECALL)")
    print("=========================================================================================================")
    y_pool = np.concatenate(pooled_y)
    amt_pool = np.concatenate(pooled_amt)
    rng = np.random.default_rng(42)

    for m in models:
        s_pool = np.concatenate(pooled_scores[m])
        ap_full = average_precision_score(y_pool, s_pool)
        rec_fpr005 = recall_at_fpr(y_pool, s_pool, 0.0005)
        rec_fpr010 = recall_at_fpr(y_pool, s_pool, 0.0010)
        rec_cnt, prec_cnt, rec_usd = dollar_recall_at_rate(y_pool, s_pool, amt_pool, 0.002)

        boot_ap, boot_rec = [], []
        for _ in range(1000):
            idx = rng.integers(0, len(y_pool), size=len(y_pool))
            if np.sum(y_pool[idx]) == 0:
                continue
            boot_ap.append(average_precision_score(y_pool[idx], s_pool[idx]))
            r_b, _, _ = dollar_recall_at_rate(y_pool[idx], s_pool[idx], amt_pool[idx], 0.002)
            boot_rec.append(r_b)

        print(
            f"  {m:<36} | PR-AUC: {ap_full:.4f} [{np.percentile(boot_ap, 2.5):.4f}, {np.percentile(boot_ap, 97.5):.4f}] | "
            f"Rec@0.05%FPR: {rec_fpr005:.1f}% | Rec@0.1%FPR: {rec_fpr010:.1f}% | "
            f"Rec@0.2%Alert: {rec_cnt:.1f}% [{np.percentile(boot_rec, 2.5):.1f}%, {np.percentile(boot_rec, 97.5):.1f}%] | "
            f"Prec@0.2%: {prec_cnt:.1f}% | DollarRec@0.2%: {rec_usd:.1f}%"
        )

    print("\n=========================================================================================================")
    print("4. CALIBRATOR COMPARISON ON POOLED OOT (NONE vs. SIGMOID/PLATT vs. ISOTONIC)")
    print("=========================================================================================================")
    for cname, pairs in cal_logs.items():
        yc = np.concatenate([p[0] for p in pairs])
        pc = np.concatenate([p[1] for p in pairs])
        print(
            f"  {cname:<16} | Pooled BSS: {brier_skill_score(yc, pc):+.4f} | "
            f"Pooled ECE: {compute_ece(yc, pc):.5f} | Unique Score Levels: {len(np.unique(np.round(pc, 6)))}"
        )
