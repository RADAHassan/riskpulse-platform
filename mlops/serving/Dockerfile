# syntax=docker/dockerfile:1.7
# Build context: repository root  ->  docker build -f mlops/serving/Dockerfile .
# Base image pinned by digest (python:3.12-slim, multi-arch index).
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY mlops/serving/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
LABEL org.opencontainers.image.source="https://github.com/RADAHassan/riskpulse-platform" \
      org.opencontainers.image.title="riskpulse-ml-serving" \
      org.opencontainers.image.licenses="MIT"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Only what inference needs: predictor, tolerant bundle loader, autoencoder (pickled in the bundle), artifacts.
COPY ml/src/__init__.py ./src/__init__.py
COPY ml/src/ml/predictor.py ml/src/ml/bundle_io.py ./src/ml/
COPY ml/src/models/__init__.py ml/src/models/autoencoder.py ./src/models/
COPY ml/artifacts/riskpulse_29d_bundle.joblib ml/artifacts/conformal.json ml/artifacts/benchmark_results.csv \
     ml/artifacts/statistical_tests.csv ml/artifacts/friedman_summary.json ml/artifacts/statistical_summary.json \
     ml/artifacts/latent_projections.json ./artifacts/
COPY ml/artifacts/figures/pca_tsne_umap.png ./artifacts/figures/
COPY ml/figures/fig_reliability.png ml/figures/fig_pr_curves.png ./figures/
COPY mlops/serving/app ./app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
