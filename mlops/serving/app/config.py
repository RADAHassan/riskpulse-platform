"""Runtime settings for ml-serving (12-factor, environment driven)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_artifacts_dir() -> Path:
    # Container: /app/artifacts. Repo checkout: <repo>/ml/artifacts.
    container = Path("/app/artifacts")
    if container.exists():
        return container
    return Path(__file__).resolve().parents[3] / "ml" / "artifacts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    service_key: str = Field(default="", description="Shared key required in X-Service-Key")
    allow_insecure_dev: bool = Field(default=False, description="Allow empty SERVICE_KEY (tests/dev only)")

    mlflow_tracking_uri: str = ""
    model_uri: str = "models:/riskpulse-fraud@champion"
    mlflow_cache_dir: str = "/tmp/mlflow-model"  # noqa: S108 - emptyDir in Kubernetes

    artifacts_dir: Path = Field(default_factory=_default_artifacts_dir)
    local_bundle_path: str = ""
    local_conformal_path: str = ""

    max_batch_size: int = 256
    max_request_bytes: int = 1_048_576

    @property
    def bundle_path(self) -> Path:
        if self.local_bundle_path:
            return Path(self.local_bundle_path)
        return self.artifacts_dir / "riskpulse_29d_bundle.joblib"

    @property
    def conformal_path(self) -> Path:
        return Path(self.local_conformal_path) if self.local_conformal_path else self.artifacts_dir / "conformal.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
