"""RiskPulse ml-serving — FastAPI inference service."""

from __future__ import annotations

import hmac
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics, reports
from .config import Settings, get_settings
from .decision import to_platform_decision
from .model_store import LoadedModel, load_model
from .schemas import BatchRequest, BatchResponse, ModelInfo, PredictRequest, PredictResponse

logger = logging.getLogger("riskpulse.serving")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _activate(app: FastAPI, model: LoadedModel) -> None:
    app.state.model = model
    metrics.set_model_info(model.version, model.source)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.service_key and not settings.allow_insecure_dev:
        raise RuntimeError("SERVICE_KEY is required (set ALLOW_INSECURE_DEV=true only for local tests)")
    app.state.model = None
    _activate(app, load_model(settings))
    yield


app = FastAPI(
    title="RiskPulse ml-serving",
    version="1.0.0",
    description="Fraud scoring with calibrated probability, uncertainty and conformal sets.",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the offending input (NaN/Inf are not JSON-serialisable and must not be reflected)."""
    detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


def require_key(
    x_service_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.service_key:  # only reachable with ALLOW_INSECURE_DEV
        return
    if x_service_key is None or not hmac.compare_digest(x_service_key.encode(), settings.service_key.encode()):
        raise HTTPException(status_code=401, detail="invalid or missing service key")


def get_model(request: Request) -> LoadedModel:
    model: LoadedModel | None = request.app.state.model
    if model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    return model


@app.middleware("http")
async def instrument(request: Request, call_next):
    settings = get_settings()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_request_bytes:
        return JSONResponse(status_code=413, content={"detail": "request too large"})
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        handler = getattr(route, "path", "unmatched")
        metrics.HTTP_REQUESTS.labels(request.method, handler, str(status)).inc()
        metrics.HTTP_DURATION.labels(request.method, handler).observe(time.perf_counter() - start)


def _score(model: LoadedModel, req: PredictRequest) -> PredictResponse:
    start = time.perf_counter()
    with model.lock:  # the research predictor keeps rolling buffers: serialise access
        res = model.predictor.score_transaction(req.amount, list(req.features))
    elapsed = time.perf_counter() - start

    decision, reason = to_platform_decision(res)
    probability = float(res["calibrated_probability"])
    metrics.INFERENCE_SECONDS.observe(elapsed)
    metrics.UNCERTAINTY.observe(float(res["uncertainty_score"]))
    metrics.PREDICTIONS.labels(decision=decision).inc()
    if decision == "HUMAN_REVIEW":
        metrics.HUMAN_REVIEW.inc()

    return PredictResponse(
        transaction_id=req.transaction_id,
        prediction=1 if probability >= 0.5 else 0,
        probability=probability,
        uncertainty=float(res["uncertainty_score"]),
        decision=decision,
        conformal_set=res["conformal_set"],
        conformal_review=bool(res["conformal_review_flag"]),
        human_review=bool(res["human_review"]),
        review_reason=reason,
        expected_loss_usd=float(res["expected_loss_usd"]),
        raw_score=float(res["raw_rank_score"]),
        model_version=model.version,
        registry_version=model.registry_version,
        model_source=model.source,
        inference_ms=round(elapsed * 1000, 3),
    )


@app.post("/predict", response_model=PredictResponse, dependencies=[Depends(require_key)])
def predict(req: PredictRequest, model: LoadedModel = Depends(get_model)) -> PredictResponse:
    return _score(model, req)


@app.post("/predict/batch", response_model=BatchResponse, dependencies=[Depends(require_key)])
def predict_batch(
    req: BatchRequest,
    model: LoadedModel = Depends(get_model),
    settings: Settings = Depends(get_settings),
) -> BatchResponse:
    if len(req.transactions) > settings.max_batch_size:
        raise HTTPException(status_code=413, detail=f"batch too large (max {settings.max_batch_size})")
    results = [_score(model, tx) for tx in req.transactions]
    return BatchResponse(count=len(results), results=results)


@app.get("/model/info", response_model=ModelInfo, dependencies=[Depends(require_key)])
def model_info(model: LoadedModel = Depends(get_model)) -> ModelInfo:
    p = model.predictor
    return ModelInfo(
        model_version=model.version,
        registry_version=model.registry_version,
        model_source=model.source,
        model_uri=model.model_uri,
        alias=model.alias,
        loaded_at=model.loaded_at,
        policy={
            "buffer_policy": p.buffer_policy,
            "queue_policy": p.queue_policy,
            "target_alert_rate": p.target_rate,
            "auto_decline_prob_guard": p.guard_prob,
            "uncertainty_review_threshold": p.uncertainty_review_threshold,
            "uncertainty_downgrade_only": p.uncertainty_downgrade_only,
            "conformal_q_legit": p.q_legit,
            "conformal_q_fraud": p.q_fraud,
            "review_threshold_raw_score": p.review_threshold,
        },
        decision_semantics={
            "DECLINE": "calibrated p >= guard AND conformal set == {FRAUD} AND uncertainty < threshold",
            "HUMAN_REVIEW": "uncertain prediction, top-0.5% raw score, or any serving failure (fallback)",
            "APPROVE": "everything else",
        },
    )


@app.post("/model/reload", response_model=ModelInfo, dependencies=[Depends(require_key)])
def model_reload(request: Request, settings: Settings = Depends(get_settings)) -> ModelInfo:
    """Re-resolve the ``champion`` alias (called by the pipeline deployment stage)."""
    _activate(request.app, load_model(settings))
    return model_info(request.app.state.model)


@app.get("/model/report", dependencies=[Depends(require_key)])
def model_report(settings: Settings = Depends(get_settings)) -> dict:
    return reports.build_report(settings.artifacts_dir)


@app.get("/model/figures/{name}", dependencies=[Depends(require_key)])
def model_figure(name: str, settings: Settings = Depends(get_settings)):
    path = reports.figure_path(name, settings.artifacts_dir)
    if path is None:
        raise HTTPException(status_code=404, detail="unknown figure")
    return FileResponse(path, media_type="image/png")


@app.get("/projections", dependencies=[Depends(require_key)])
def projections(settings: Settings = Depends(get_settings)) -> dict:
    data = reports.projections(settings.artifacts_dir)
    if not data:
        raise HTTPException(status_code=404, detail="projections artifact missing")
    return data


@app.get("/health/live")
def live() -> dict:
    return {"status": "UP"}


@app.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    model: LoadedModel | None = request.app.state.model
    if model is None:
        return JSONResponse(status_code=503, content={"status": "DOWN"})
    return JSONResponse(content={"status": "UP", "model_version": model.version, "source": model.source})


@app.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)
