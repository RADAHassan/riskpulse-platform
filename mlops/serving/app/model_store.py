"""Model loading: MLflow ``champion`` alias first, local bundle as fallback.

The served object is ``RiskPulseMLPredictor`` (ml/src/ml/predictor.py). MLflow stores the bundle and the
conformal quantiles as artifacts of a pyfunc model; the registry version is reported in every response.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings

logger = logging.getLogger("riskpulse.serving")

BUNDLE_NAME = "riskpulse_29d_bundle.joblib"
CONFORMAL_NAME = "conformal.json"


@dataclass
class LoadedModel:
    predictor: object
    version: str
    registry_version: str | None
    source: str  # "mlflow" | "local-bundle"
    model_uri: str
    alias: str | None
    loaded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    lock: threading.Lock = field(default_factory=threading.Lock)


def _new_predictor(bundle: Path, conformal: Path):
    from src.ml.predictor import RiskPulseMLPredictor  # imported lazily: pulls torch/xgboost

    return RiskPulseMLPredictor(bundle_path=str(bundle), conformal_path=str(conformal))


def _parse_model_uri(uri: str) -> tuple[str, str | None, str | None]:
    """``models:/name@alias`` or ``models:/name/3`` -> (name, alias, version)."""
    body = uri.removeprefix("models:/")
    if "@" in body:
        name, alias = body.split("@", 1)
        return name, alias, None
    if "/" in body:
        name, version = body.split("/", 1)
        return name, None, version
    return body, None, None


def _load_from_mlflow(settings: Settings) -> LoadedModel:
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient()
    name, alias, version = _parse_model_uri(settings.model_uri)
    mv = client.get_model_version_by_alias(name, alias) if alias else client.get_model_version(name, version)
    dst = Path(settings.mlflow_cache_dir) / f"v{mv.version}"
    dst.mkdir(parents=True, exist_ok=True)
    local = Path(mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{name}/{mv.version}", dst_path=str(dst)))
    bundle = next(local.rglob(BUNDLE_NAME))
    conformal = next(local.rglob(CONFORMAL_NAME))
    predictor = _new_predictor(bundle, conformal)
    return LoadedModel(
        predictor=predictor,
        version=predictor.version,
        registry_version=str(mv.version),
        source="mlflow",
        model_uri=settings.model_uri,
        alias=alias,
    )


def _load_local(settings: Settings) -> LoadedModel:
    predictor = _new_predictor(settings.bundle_path, settings.conformal_path)
    return LoadedModel(
        predictor=predictor,
        version=predictor.version,
        registry_version=None,
        source="local-bundle",
        model_uri=str(settings.bundle_path),
        alias=None,
    )


def load_model(settings: Settings) -> LoadedModel:
    if settings.mlflow_tracking_uri:
        try:
            model = _load_from_mlflow(settings)
            logger.info("Loaded %s v%s from MLflow (%s)", model.version, model.registry_version, model.model_uri)
            return model
        except Exception as exc:  # noqa: BLE001 - any registry failure must fall back
            logger.warning("MLflow model unavailable (%s: %s); falling back to local bundle", type(exc).__name__, exc)
    model = _load_local(settings)
    logger.info("Loaded %s from local bundle", model.version)
    return model
