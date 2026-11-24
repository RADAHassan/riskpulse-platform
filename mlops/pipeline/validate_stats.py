"""Stage 3 — Statistical validation gate.

Reads the Friedman / Wilcoxon-Holm / conformal artifacts and evaluates explicit promotion gates.
The candidate is promoted to ``champion`` only if **all** gates pass.

Gates (thresholds are explicit and versioned here):
  G1  no competitor is significantly better than XGBoost (Holm-adjusted p < 0.05 AND higher mean PR-AUC)
  G2  isotonic calibration improves Brier score vs raw scores
  G3  conformal coverage on the served block: legit >= 0.99 and fraud >= 0.80
  G4  single-transaction latency <= 1.0 ms
  G5  omnibus Friedman test (all models) reported (p-value present) — statistical evidence is on record
"""

from __future__ import annotations

import csv
import json

import mlflow
from common import ARTIFACTS, Context, log_json_artifact, start_stage

ALPHA = 0.05
MIN_LEGIT_COVERAGE = 0.99
MIN_FRAUD_COVERAGE = 0.80
MAX_LATENCY_MS = 1.0


def evaluate_gates(tests: list[dict], friedman: dict, conformal: dict, benchmark_xgb: dict) -> dict:
    inferior = [
        t["Comparison"]
        for t in tests
        if float(t["adjusted_p_value"]) < ALPHA and float(t["Other_Mean_PR_AUC"]) > float(t["XGBoost_Mean_PR_AUC"])
    ]
    serving = conformal.get("serving_oot_evaluation", {})
    gates = {
        "G1_xgboost_not_significantly_inferior": {
            "passed": not inferior,
            "detail": {"significantly_better_competitors": inferior, "alpha": ALPHA, "correction": "Holm"},
        },
        "G2_calibration_improves_brier": {
            "passed": float(benchmark_xgb["Brier_Calibrated"]) < float(benchmark_xgb["Brier_Raw"]),
            "detail": {"raw": benchmark_xgb["Brier_Raw"], "calibrated": benchmark_xgb["Brier_Calibrated"]},
        },
        "G3_conformal_coverage": {
            "passed": serving.get("empirical_coverage_legit", 0) >= MIN_LEGIT_COVERAGE
            and serving.get("empirical_coverage_fraud", 0) >= MIN_FRAUD_COVERAGE,
            "detail": {
                "legit": serving.get("empirical_coverage_legit"),
                "fraud": serving.get("empirical_coverage_fraud"),
                "min_legit": MIN_LEGIT_COVERAGE,
                "min_fraud": MIN_FRAUD_COVERAGE,
            },
        },
        "G4_latency": {
            "passed": float(benchmark_xgb["Single_Txn_Latency_ms"]) <= MAX_LATENCY_MS,
            "detail": {"single_txn_ms": benchmark_xgb["Single_Txn_Latency_ms"], "max_ms": MAX_LATENCY_MS},
        },
        "G5_omnibus_test_on_record": {
            "passed": "p_value" in friedman.get("friedman_5_models", {}),
            "detail": friedman.get("friedman_5_models", {}),
        },
    }
    return gates


def run(ctx: Context) -> Context:
    with (ARTIFACTS / "statistical_tests.csv").open(newline="", encoding="utf-8") as fh:
        tests = list(csv.DictReader(fh))
    friedman = json.loads((ARTIFACTS / "friedman_summary.json").read_text(encoding="utf-8"))
    conformal = json.loads((ARTIFACTS / "conformal.json").read_text(encoding="utf-8"))
    benchmark_xgb = ctx.metrics.get("evaluation", {}).get("benchmark_xgb")
    if benchmark_xgb is None:
        from evaluate import read_benchmark

        benchmark_xgb = next(r for r in read_benchmark() if r["Model"] == "XGBoost")

    gates = evaluate_gates(tests, friedman, conformal, benchmark_xgb)
    passed = all(g["passed"] for g in gates.values())

    with start_stage("statistical_validation", ctx):
        mlflow.log_metric("friedman_5_models_chi2", friedman["friedman_5_models"]["chi2"])
        mlflow.log_metric("friedman_5_models_p", friedman["friedman_5_models"]["p_value"])
        mlflow.log_metric("friedman_4_models_no_svm_p", friedman["friedman_4_models_no_svm"]["p_value"])
        for t in tests:
            key = t["Comparison"].replace(" ", "_").replace("(", "").replace(")", "")
            mlflow.log_metric(f"wilcoxon_adj_p__{key}", float(t["adjusted_p_value"]))
            mlflow.log_metric(f"cliffs_delta__{key}", float(t["Cliffs_Delta"]))
        for name, g in gates.items():
            mlflow.log_metric(f"gate_{name.split('_')[0]}", 1.0 if g["passed"] else 0.0)
        mlflow.log_metric("gates_passed", 1.0 if passed else 0.0)
        mlflow.set_tag("promotion_decision", "champion" if passed else "challenger")
        log_json_artifact(gates, "statistical_validation_gates.json", ctx)
        for name in ("statistical_tests.csv", "friedman_summary.json", "statistical_summary.json", "conformal.json"):
            mlflow.log_artifact(str(ARTIFACTS / name), "statistics")

    ctx.gates, ctx.gates_passed = gates, passed
    return ctx


if __name__ == "__main__":
    c = Context.load()
    run(c)
    c.save()
