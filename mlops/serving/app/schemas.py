"""Pydantic v2 request/response models (see docs/contracts/predict-*.schema.json)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

N_FEATURES = 28  # V1..V28 (Amount is a separate field)

Finite = Annotated[float, Field(allow_inf_nan=False)]
Decision = Literal["APPROVE", "HUMAN_REVIEW", "DECLINE"]


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str | None = Field(default=None, max_length=64)
    amount: Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]
    features: list[Finite] = Field(min_length=N_FEATURES, max_length=N_FEATURES)


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactions: list[PredictRequest] = Field(min_length=1)


class PredictResponse(BaseModel):
    transaction_id: str | None = None
    prediction: Literal[0, 1]
    probability: float
    uncertainty: float
    decision: Decision
    conformal_set: list[Literal["LEGIT", "FRAUD"]]
    conformal_review: bool
    human_review: bool
    review_reason: str
    expected_loss_usd: float
    raw_score: float
    model_version: str
    registry_version: str | None = None
    model_source: Literal["mlflow", "local-bundle"]
    inference_ms: float


class BatchResponse(BaseModel):
    count: int
    results: list[PredictResponse]


class ModelInfo(BaseModel):
    model_version: str
    registry_version: str | None
    model_source: Literal["mlflow", "local-bundle"]
    model_uri: str
    alias: str | None
    loaded_at: str
    policy: dict
    decision_semantics: dict
