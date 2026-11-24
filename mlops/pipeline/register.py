"""Stage 4 — Model registry: log the pyfunc model, register ``riskpulse-fraud`` and set the alias.

``champion`` is only set when the statistical gates passed; otherwise the version gets ``challenger``.
"""

from __future__ import annotations

import mlflow
import pandas as pd
from common import CHALLENGER_ALIAS, CHAMPION_ALIAS, ML_DIR, REGISTERED_MODEL, Context, start_stage, tracking_uri
from mlflow import MlflowClient
from mlflow.models import infer_signature
from pyfunc_model import RiskPulsePyfunc


def run(ctx: Context) -> Context:
    if ctx.gates_passed is None:
        raise SystemExit("register needs the validation stage first (ctx.gates_passed is None)")

    example = pd.DataFrame([{"amount": 149.99, **{f"v{i}": 0.0 for i in range(1, 29)}}])
    signature = infer_signature(example, pd.DataFrame([{"probability": 0.0, "uncertainty": 0.0,
                                                        "decision": "APPROVE", "model_version": "x"}]))
    with start_stage("registry", ctx) as run_:
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=RiskPulsePyfunc(),
            artifacts={"bundle": ctx.bundle_path, "conformal": ctx.conformal_path},
            code_paths=[str(ML_DIR / "src")],
            signature=signature,
            input_example=example,
            pip_requirements=str(ML_DIR / "requirements.txt"),
            registered_model_name=REGISTERED_MODEL,
        )
        client = MlflowClient(tracking_uri())
        mv = max(client.search_model_versions(f"name='{REGISTERED_MODEL}'"), key=lambda m: int(m.version))
        for key, value in {
            "gates_passed": str(ctx.gates_passed),
            "pipeline_mode": ctx.mode,
            "model_run_id": run_.info.run_id,
            "model_uri": info.model_uri,
        }.items():
            client.set_model_version_tag(REGISTERED_MODEL, mv.version, key, value)
        for gate, result in ctx.gates.items():
            client.set_model_version_tag(REGISTERED_MODEL, mv.version, f"gate.{gate}", str(result["passed"]))

        alias = CHAMPION_ALIAS if ctx.gates_passed else CHALLENGER_ALIAS
        client.set_registered_model_alias(REGISTERED_MODEL, alias, mv.version)
        mlflow.set_tag("registered_version", mv.version)
        mlflow.set_tag("alias", alias)

    ctx.model_version, ctx.alias = str(mv.version), alias
    print(f"Registered {REGISTERED_MODEL} v{mv.version} -> alias '{alias}'")
    return ctx


if __name__ == "__main__":
    c = Context.load()
    run(c)
    c.save()
