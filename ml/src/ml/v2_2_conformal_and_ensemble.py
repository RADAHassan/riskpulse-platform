"""
RiskPulse v2.3.5 — Task 4: Mondrian Split-Conformal (Continuous Raw-Score Nonconformity)
Uses strictly disjoint chronological splits and continuous raw rank scores for conformal
quantiles (avoiding Isotonic step collapse), plus set-efficiency metrics and policy replay.
"""
import json, joblib, sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
import xgboost as xgb

warnings.filterwarnings("ignore")
SEEDS = [7, 21, 42, 84, 128]
ALPHA_LEGIT, ALPHA_FRAUD = 0.005, 0.150


def conformal_quantile(scores, alpha):
    n = len(scores)
    if n == 0:
        return 1.0
    level = min(1.0, np.ceil((n + 1) * (1.0 - alpha)) / n)
    return float(np.quantile(scores, level, method="higher"))


def set_efficiency(i0, i1, y):
    sizes = i0.astype(int) + i1.astype(int)
    rev = sizes != 1
    singleton_rate = float(np.mean(sizes == 1))
    avg_set_size = float(np.mean(sizes))
    fraud_in_rev = float(np.mean(y[rev] == 1)) if rev.sum() > 0 else 0.0
    return {
        "singleton_rate": round(singleton_rate, 4),
        "avg_set_size": round(avg_set_size, 4),
        "fraud_rate_in_reviews": round(fraud_in_rev, 5),
    }


def fit_xgb_and_iso(X_tr, y_tr, X_iso, y_iso, seed):
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=220, max_depth=3, learning_rate=0.05, subsample=0.8,
        colsample_bytree=0.8, scale_pos_weight=spw, eval_metric="logloss",
        random_state=seed, n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(model.predict_proba(X_iso)[:, 1], y_iso)
    return model, iso


def replay_policy(oot_df, use_uncertainty_routing, uncertainty_downgrade_only=True):
    from src.ml.predictor import RiskPulseMLPredictor
    p = RiskPulseMLPredictor(
        use_uncertainty_routing=use_uncertainty_routing,
        uncertainty_downgrade_only=uncertainty_downgrade_only,
    )
    y_true = oot_df["Class"].values
    decs, max_u = [], 0.0
    for row in oot_df.itertuples(index=False):
        r = p.score_transaction(float(row.Amount), [float(getattr(row, f"V{i}")) for i in range(1, 29)])
        decs.append(r["decision"])
        max_u = max(max_u, r["human_queue_utilization"])
    decs = np.array(decs)
    flagged = decs != "APPROVE"
    tp = int((flagged & (y_true == 1)).sum())
    return {
        "n_test": int(len(y_true)),
        "n_frauds": int(y_true.sum()),
        "auto_declines": int((decs == "AUTO_DECLINE").sum()),
        "manual_reviews": int((decs == "MANUAL_REVIEW").sum()),
        "combined_recall": round(tp / max(int(y_true.sum()), 1), 4),
        "combined_precision": round(tp / max(int(flagged.sum()), 1), 4),
        "max_human_queue_utilization": round(float(max_u), 4),
    }


def main():
    Path("artifacts").mkdir(exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all, y_all, n = df[cols].values, df["Class"].values, len(df)

    windows = [
        ("W1 [60%-73%]", int(0.50 * n), int(0.60 * n), int(0.73 * n)),
        ("W2 [73%-86%]", int(0.63 * n), int(0.73 * n), int(0.86 * n)),
        ("W3 [86%-100%]", int(0.76 * n), int(0.86 * n), n),
    ]
    win_res, py, pin, pi0, pi1, pstd = [], [], [], [], [], []
    print("Running Mondrian Split-Conformal (continuous raw_score nonconformity)...")
    for name, tr_e, cal_e, te_e in windows:
        iso_e = tr_e + (cal_e - tr_e) // 2
        X_tr, y_tr = X_all[:tr_e], y_all[:tr_e]
        X_iso, y_iso = X_all[tr_e:iso_e], y_all[tr_e:iso_e]
        X_cf, y_cf = X_all[iso_e:cal_e], y_all[iso_e:cal_e]
        X_te, y_te = X_all[cal_e:te_e], y_all[cal_e:te_e]

        cf_raw_s, te_raw_s, te_cal_s = [], [], []
        for s in SEEDS:
            m, iso = fit_xgb_and_iso(X_tr, y_tr, X_iso, y_iso, s)
            cf_raw_s.append(m.predict_proba(X_cf)[:, 1])
            r_te = m.predict_proba(X_te)[:, 1]
            te_raw_s.append(r_te)
            te_cal_s.append(iso.predict(r_te))

        r_cf = np.vstack(cf_raw_s).mean(axis=0)
        r_te = np.vstack(te_raw_s).mean(axis=0)
        s_std = np.vstack(te_cal_s).std(axis=0)

        q0 = conformal_quantile(r_cf[y_cf == 0], ALPHA_LEGIT)
        q1 = conformal_quantile(1.0 - r_cf[y_cf == 1], ALPHA_FRAUD)
        i0, i1 = r_te <= q0, (1.0 - r_te) <= q1
        rev = (i0.astype(int) + i1.astype(int)) != 1
        ins = np.where(y_te == 1, i1, i0)
        eff = set_efficiency(i0, i1, y_te)

        win_res.append({
            "window": name, "n_conf_frauds": int(y_cf.sum()),
            "n_test": int(len(y_te)), "n_test_frauds": int(y_te.sum()),
            "q_legit": round(q0, 5), "q_fraud": round(q1, 5),
            "empirical_coverage_overall": round(float(np.mean(ins)), 4),
            "empirical_coverage_legit": round(float(np.mean(ins[y_te == 0])), 4),
            "empirical_coverage_fraud": round(float(np.mean(ins[y_te == 1])), 4),
            "human_review_count": int(rev.sum()), "human_review_rate_pct": round(float(np.mean(rev) * 100), 3),
            **eff,
            "seed_variance_std_legit": round(float(np.mean(s_std[y_te == 0])), 5),
            "seed_variance_std_fraud": round(float(np.mean(s_std[y_te == 1])), 5),
            "seed_variance_std_review_cases": round(float(np.mean(s_std[rev])) if rev.sum() else 0.0, 5),
        })
        py.append(y_te); pin.append(ins); pi0.append(i0); pi1.append(i1); pstd.append(s_std)
        print(f"  {name} | Fraud Cov:{np.mean(ins[y_te==1])*100:5.1f}% | Legit Cov:{np.mean(ins[y_te==0])*100:6.2f}% | Rev:{np.mean(rev)*100:5.2f}% | Singleton:{eff['singleton_rate']*100:5.2f}%")

    py, pin, pi0, pi1, pstd = map(np.concatenate, (py, pin, pi0, pi1, pstd))
    prev = (pi0.astype(int) + pi1.astype(int)) != 1
    peff = set_efficiency(pi0, pi1, py)

    # Served canonical bundle: XGB [0-70%], Iso [70-85%], Conformal cal [85-90%], OOT eval [90-100%]
    b = joblib.load("artifacts/riskpulse_29d_bundle.joblib")
    c0, c1 = int(0.85 * n), int(0.90 * n)
    Xb_c, yb_c = X_all[c0:c1].copy(), y_all[c0:c1]
    Xb_t, yb_t = X_all[c1:].copy(), y_all[c1:]
    Xb_c[:, 0] = b["scaler"].transform(Xb_c[:, [0]]).ravel()
    Xb_t[:, 0] = b["scaler"].transform(Xb_t[:, [0]]).ravel()
    rb_c = b["xgb_model"].predict_proba(Xb_c)[:, 1]
    rb_t = b["xgb_model"].predict_proba(Xb_t)[:, 1]
    pb_t = b["isotonic_calibrator"].predict(rb_t)

    q0_s = conformal_quantile(rb_c[yb_c == 0], ALPHA_LEGIT)
    q1_s = conformal_quantile(1.0 - rb_c[yb_c == 1], ALPHA_FRAUD)
    i0_s, i1_s = rb_t <= q0_s, (1.0 - rb_t) <= q1_s
    ins_s = np.where(yb_t == 1, i1_s, i0_s)
    rev_s = (i0_s.astype(int) + i1_s.astype(int)) != 1
    eff_s = set_efficiency(i0_s, i1_s, yb_t)
    unc_s = 2.0 * np.minimum(pb_t, 1.0 - pb_t)
    down_s = (pb_t >= b["policy_config"]["auto_decline_prob_guard"]) & (unc_s >= 0.25)

    out = {
        "method": "Mondrian split-conformal on continuous raw_score (disjoint splits) + 5-seed offline variance",
        "nonconformity_score": "1 - raw_score(true_class)",
        "seeds": SEEDS,
        "target_coverage": {"legit_class_0": 1.0 - ALPHA_LEGIT, "fraud_class_1": 1.0 - ALPHA_FRAUD},
        "serving_quantiles": {
            "source_model": b["model_version"], "calibration_block": "[85%-90%] deduplicated ULB",
            "n_cal_frauds": int(yb_c.sum()), "q_legit": round(q0_s, 5), "q_fraud": round(q1_s, 5),
        },
        "serving_oot_evaluation": {
            "oot_block": "[90%-100%] deduplicated ULB", "n_test": int(len(yb_t)), "n_test_frauds": int(yb_t.sum()),
            "empirical_coverage_legit": round(float(np.mean(ins_s[yb_t == 0])), 4),
            "empirical_coverage_fraud": round(float(np.mean(ins_s[yb_t == 1])), 4),
            "conformal_review_count": int(rev_s.sum()),
            "conformal_review_rate_pct": round(float(np.mean(rev_s) * 100), 3),
            **eff_s,
            "uncertainty_downgraded_from_auto_decline": int(down_s.sum()),
        },
        "pooled_oot": {
            "total_txns": int(len(py)), "total_frauds": int(py.sum()),
            "empirical_coverage_overall": round(float(np.mean(pin)), 4),
            "empirical_coverage_legit": round(float(np.mean(pin[py == 0])), 4),
            "empirical_coverage_fraud": round(float(np.mean(pin[py == 1])), 4),
            "total_human_reviews": int(prev.sum()), "human_review_rate_pct": round(float(np.mean(prev) * 100), 3),
            **peff,
            "seed_variance_std_legit": round(float(np.mean(pstd[py == 0])), 5),
            "seed_variance_std_fraud": round(float(np.mean(pstd[py == 1])), 5),
            "seed_variance_std_review_cases": round(float(np.mean(pstd[prev])) if prev.sum() else 0.0, 5),
        },
        "windows": win_res,
    }
    Path("artifacts/conformal.json").write_text(json.dumps(out, indent=2))

    oot_df = df.iloc[c1:]
    out["policy_replay_comparison"] = {
        "oot_block": "[90%-100%] deduplicated ULB (22-fraud smoke test)",
        "baseline_two_tier": replay_policy(oot_df, use_uncertainty_routing=False, uncertainty_downgrade_only=True),
        "guard_only_uncertainty_default": replay_policy(oot_df, use_uncertainty_routing=True, uncertainty_downgrade_only=True),
        "full_band_uncertainty": replay_policy(oot_df, use_uncertainty_routing=True, uncertainty_downgrade_only=False),
    }
    Path("artifacts/conformal.json").write_text(json.dumps(out, indent=2))
    print("\n=== POOLED OOT ===", json.dumps(out["pooled_oot"], indent=2))
    print("\n=== SERVING QUANTILES ===", json.dumps(out["serving_quantiles"], indent=2))
    print("\n=== SERVING OOT EVAL ===", json.dumps(out["serving_oot_evaluation"], indent=2))
    print("\n=== POLICY REPLAY ===", json.dumps(out["policy_replay_comparison"], indent=2))


if __name__ == "__main__":
    main()
