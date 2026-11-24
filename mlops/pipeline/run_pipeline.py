"""RiskPulse MLOps pipeline orchestrator.

    Training -> Evaluation -> Statistical Validation -> Model Registry -> Deployment

Usage (from the repo root, with the ML virtualenv):

    python mlops/pipeline/run_pipeline.py                       # auto: train if the dataset exists, else import
    python mlops/pipeline/run_pipeline.py --mode import         # log the shipped results + bundle, no retraining
    python mlops/pipeline/run_pipeline.py --stages evaluate validate

Environment: MLFLOW_TRACKING_URI (default: local SQLite file), SERVING_URL + SERVICE_KEY (deployment stage).
The process exits with code 0 when all requested stages ran, 2 when the candidate failed the validation gates
(it is then registered with the ``challenger`` alias and NOT deployed).
"""

from __future__ import annotations

import argparse
import sys

import deploy
import evaluate
import mlflow
import register
import train
import validate_stats
from common import EXPERIMENT, Context, resolve_mode, tracking_uri

STAGES = {
    "train": train.run,
    "evaluate": evaluate.run,
    "validate": validate_stats.run,
    "register": register.run,
    "deploy": deploy.run,
}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # MLflow prints emoji; Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["auto", "train", "import"], default="auto")
    ap.add_argument("--stages", nargs="+", choices=list(STAGES), default=list(STAGES))
    args = ap.parse_args(argv)

    mlflow.set_tracking_uri(tracking_uri())
    experiment = mlflow.set_experiment(EXPERIMENT)
    ctx = Context(mode=resolve_mode(args.mode), experiment_id=experiment.experiment_id)

    with mlflow.start_run(run_name=f"pipeline-{ctx.mode}", tags={"pipeline": "riskpulse", "mode": ctx.mode}) as parent:
        ctx.parent_run_id = parent.info.run_id
        for name in args.stages:
            print(f"==> stage: {name} (mode={ctx.mode})")
            ctx = STAGES[name](ctx)
            ctx.save()
        mlflow.set_tag("gates_passed", str(ctx.gates_passed))
        if ctx.model_version:
            mlflow.set_tag("registered_version", ctx.model_version)
        print(f"Pipeline run {parent.info.run_id} finished: gates_passed={ctx.gates_passed} "
              f"model_version={ctx.model_version} alias={ctx.alias} deployed={ctx.deployed}")
    return 0 if ctx.gates_passed in (True, None) else 2


if __name__ == "__main__":
    sys.exit(main())
