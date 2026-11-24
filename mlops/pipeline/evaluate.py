"""Stage 2 — Evaluation: log benchmark metrics of the candidate model to MLflow.

Import mode reads the committed result tables (``ml/artifacts/benchmark_results.csv`` + the shipped-model
addenda copied from ``ml/README.md`` into ``reference_metrics.json``). Train mode adds metrics computed on
the chronological hold-out by ``train.py``. Nothing is recomputed or altered in import mode.
"""

from __future__ import annotations

import csv
import json

import mlflow
from common import ARTIFACTS, HERE, Context, flat, log_json_artifact, start_stage

CALIBRATION_FIGURE = ARTIFACTS.parent / "figures" / "fig_reliability.png"
PR_FIGURE = ARTIFACTS.parent / "figures" / "fig_pr_curves.png"
LATENT_FIGURE = ARTIFACTS / "figures" / "pca_tsne_umap.png"


def read_benchmark() -> list[dict]:
    with (ARTIFACTS / "benchmark_results.csv").open(newline="", encoding="utf-8") as fh:
        rows = []
        for row in csv.DictReader(fh):
            rows.append({k: (float(v) if k != "Model" else v) for k, v in row.items()})
        return rows


def run(ctx: Context) -> Context:
    reference = json.loads((HERE / "reference_metrics.json").read_text(encoding="utf-8"))
    benchmark = read_benchmark()
    xgb = next(r for r in benchmark if r["Model"] == "XGBoost")

    with start_stage("evaluation", ctx):
        # Benchmark protocol row for XGBoost (10 expanding OOT windows, 5 seeds)
        mlflow.log_metrics({
            "benchmark_pr_auc": xgb["PR-AUC"],
            "benchmark_pr_auc_ci_low": xgb["PR-AUC_Window_95CI_Low"],
            "benchmark_pr_auc_ci_high": xgb["PR-AUC_Window_95CI_High"],
            "benchmark_roc_auc": xgb["ROC-AUC"],
            "benchmark_f1_at_0_20pct": xgb["F1@0.20%"],
            "benchmark_mcc_at_0_20pct": xgb["MCC@0.20%"],
            "benchmark_brier_calibrated": xgb["Brier_Calibrated"],
            "benchmark_brier_raw": xgb["Brier_Raw"],
            "benchmark_single_txn_latency_ms": xgb["Single_Txn_Latency_ms"],
        })
        # Shipped model (served bundle) — values quoted from ml/README.md v2.3.8
        shipped = reference["shipped_xgboost"]
        mlflow.log_metrics(flat("shipped_", shipped))
        mlflow.log_metrics(flat("calibration_", reference["calibration_disjoint_oot"]))
        mlflow.log_metrics(flat("router_", reference["human_review_router_policy_c"]))
        # Metrics measured in train mode on the hold-out (absent in import mode)
        if ctx.metrics.get("train"):
            mlflow.log_metrics(flat("holdout_", ctx.metrics["train"]))

        for row in benchmark:  # one metric family per model so runs are comparable in the UI
            tag = row["Model"].lower().replace(" ", "_").replace("(", "").replace(")", "")
            mlflow.log_metrics({
                f"model_{tag}_pr_auc": row["PR-AUC"],
                f"model_{tag}_brier_cal": row["Brier_Calibrated"],
            })

        log_json_artifact(benchmark, "benchmark_results.json", ctx)
        mlflow.log_artifact(str(ARTIFACTS / "benchmark_results.csv"), "evaluation")
        for fig in (CALIBRATION_FIGURE, PR_FIGURE, LATENT_FIGURE):
            if fig.exists():
                mlflow.log_artifact(str(fig), "figures")

    ctx.metrics["evaluation"] = {
        "benchmark_xgb": xgb,
        "shipped": shipped,
        "calibration": reference["calibration_disjoint_oot"],
    }
    return ctx


if __name__ == "__main__":
    c = Context.load()
    run(c)
    c.save()
