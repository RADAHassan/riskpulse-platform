import copy
import csv
import json

from common import ARTIFACTS
from validate_stats import evaluate_gates


def load():
    with (ARTIFACTS / "statistical_tests.csv").open(newline="", encoding="utf-8") as fh:
        tests = list(csv.DictReader(fh))
    friedman = json.loads((ARTIFACTS / "friedman_summary.json").read_text(encoding="utf-8"))
    conformal = json.loads((ARTIFACTS / "conformal.json").read_text(encoding="utf-8"))
    with (ARTIFACTS / "benchmark_results.csv").open(newline="", encoding="utf-8") as fh:
        xgb = next(r for r in csv.DictReader(fh) if r["Model"] == "XGBoost")
    xgb = {k: (float(v) if k != "Model" else v) for k, v in xgb.items()}
    return tests, friedman, conformal, xgb


def test_shipped_artifacts_pass_all_gates():
    gates = evaluate_gates(*load())
    assert all(g["passed"] for g in gates.values()), {k: v for k, v in gates.items() if not v["passed"]}


def test_g1_fails_when_a_competitor_is_significantly_better():
    tests, friedman, conformal, xgb = load()
    tests = copy.deepcopy(tests)
    tests[1]["adjusted_p_value"] = "0.01"
    tests[1]["Other_Mean_PR_AUC"] = "0.90"
    gates = evaluate_gates(tests, friedman, conformal, xgb)
    assert not gates["G1_xgboost_not_significantly_inferior"]["passed"]


def test_g1_ignores_significant_wins_of_xgboost():
    tests, friedman, conformal, xgb = load()
    assert any(float(t["adjusted_p_value"]) < 0.05 for t in tests)  # XGBoost beats SVM significantly
    assert evaluate_gates(tests, friedman, conformal, xgb)["G1_xgboost_not_significantly_inferior"]["passed"]


def test_g2_fails_if_calibration_does_not_help():
    tests, friedman, conformal, xgb = load()
    xgb = {**xgb, "Brier_Calibrated": xgb["Brier_Raw"] + 1}
    assert not evaluate_gates(tests, friedman, conformal, xgb)["G2_calibration_improves_brier"]["passed"]


def test_g3_fails_on_low_coverage():
    tests, friedman, conformal, xgb = load()
    conformal = copy.deepcopy(conformal)
    conformal["serving_oot_evaluation"]["empirical_coverage_legit"] = 0.90
    assert not evaluate_gates(tests, friedman, conformal, xgb)["G3_conformal_coverage"]["passed"]


def test_g4_fails_on_slow_model():
    tests, friedman, conformal, xgb = load()
    xgb = {**xgb, "Single_Txn_Latency_ms": 5.0}
    assert not evaluate_gates(tests, friedman, conformal, xgb)["G4_latency"]["passed"]
