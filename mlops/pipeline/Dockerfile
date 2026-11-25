# syntax=docker/dockerfile:1.7
# One-shot job: Training -> Evaluation -> Statistical validation -> Registry -> Deployment.
# Build context: repository root.
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY mlops/pipeline/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip /opt/venv/bin/pip install -r /tmp/requirements.txt

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
LABEL org.opencontainers.image.source="https://github.com/RADAHassan/riskpulse-platform" \
      org.opencontainers.image.title="riskpulse-mlops-pipeline"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    PIPELINE_WORKDIR=/tmp MLFLOW_DISABLE_AGENT_HINT=1 MPLCONFIGDIR=/tmp
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY ml/src ./ml/src
COPY ml/artifacts ./ml/artifacts
COPY ml/figures ./ml/figures
COPY mlops/pipeline/*.py mlops/pipeline/reference_metrics.json ./mlops/pipeline/
USER 10001:10001
CMD ["python", "mlops/pipeline/run_pipeline.py", "--mode", "import"]
