# syntax=docker/dockerfile:1.7
# MLflow tracking + registry server (PostgreSQL backend, proxied artifact store on a volume).
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY mlops/mlflow/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
LABEL org.opencontainers.image.source="https://github.com/RADAHassan/riskpulse-platform" \
      org.opencontainers.image.title="riskpulse-mlflow"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /mlartifacts && chown 10001:10001 /mlartifacts
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    MLFLOW_DISABLE_AGENT_HINT=1
COPY --from=builder /opt/venv /opt/venv
USER 10001:10001
EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)"]
# MLFLOW_BACKEND_STORE_URI and MLFLOW_ALLOWED_HOSTS are provided by the orchestrator (secret / configmap).
CMD ["sh", "-c", "exec mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri \"$MLFLOW_BACKEND_STORE_URI\" --artifacts-destination /mlartifacts --serve-artifacts --allowed-hosts \"$MLFLOW_ALLOWED_HOSTS\" --workers 1"]
