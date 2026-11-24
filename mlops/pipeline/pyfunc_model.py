"""MLflow pyfunc wrapper around the RiskPulse predictor (bundle + conformal quantiles as artifacts)."""

from __future__ import annotations

import mlflow.pyfunc
import pandas as pd


class RiskPulsePyfunc(mlflow.pyfunc.PythonModel):
    """Input columns: ``amount`` and ``v1``..``v28``. Output: probability, uncertainty, decision."""

    def load_context(self, context):
        from src.ml.predictor import RiskPulseMLPredictor

        self.predictor = RiskPulseMLPredictor(
            bundle_path=context.artifacts["bundle"], conformal_path=context.artifacts["conformal"]
        )

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        rows = []
        for _, r in model_input.iterrows():
            out = self.predictor.score_transaction(float(r["amount"]), [float(r[f"v{i}"]) for i in range(1, 29)])
            rows.append({
                "probability": out["calibrated_probability"],
                "uncertainty": out["uncertainty_score"],
                "decision": out["decision"],
                "model_version": out["model_version"],
            })
        return pd.DataFrame(rows)
