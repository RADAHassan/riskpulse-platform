# RiskPulse — High-Availability MLOps FinTech Platform

Fraud/risk classification platform combining **Spring Boot microservices**, a **React** dashboard,
**statistically validated ML** with **uncertainty quantification**, **MLflow / FastAPI** model serving,
and a **Kubernetes** deployment supervised by **Prometheus + Grafana**, delivered through a
**DevSecOps CI/CD** pipeline.

> Projet ML — JEE / LSI 2026 · Équipe de 5 · Deadline : **10/01/2027**

---

## Architecture (target)

```
                 ┌──────────────┐
  Browser ──────►│  React (UI)  │
                 └──────┬───────┘
                        │ HTTPS (Ingress)
                 ┌──────▼───────┐
                 │ API Gateway  │  JWT validation, routing, rate limiting
                 └──────┬───────┘
   ┌──────────┬─────────┼──────────┬───────────────┬──────────────┐
   ▼          ▼         ▼          ▼               ▼              ▼
 auth    customer  transaction   risk ───────► ml-serving    notification / audit
                                   │  REST      (FastAPI)
                                   │            prediction, probability,
                                   │            uncertainty, model version
                                   ▼                 ▲
                               PostgreSQL       MLflow Model Registry

  Observability: Prometheus ◄── /actuator/prometheus, /metrics, kube-state-metrics, node-exporter
                 Grafana dashboards + Alertmanager (CPU > 80 %, p95 > 2 s, errors > 5 %, pod down…)
```

## Repository layout

| Path | Content | Project tasks | Owner |
| :--- | :--- | :---: | :--- |
| [`backend/`](backend/) | Spring Boot microservices + API Gateway | 1 | Backend |
| [`frontend/`](frontend/) | React dashboard (risk, uncertainty, PCA/t-SNE/UMAP views) | 7 (UI) | Frontend |
| [`ml/`](ml/) | Research, benchmarking, statistical validation, uncertainty, model artifacts | 2, 3, 4, 7 | ML |
| [`mlops/`](mlops/) | MLflow tracking/registry, reproducible pipeline, FastAPI serving | 5, 6 | MLOps |
| [`infra/`](infra/) | Docker, Kubernetes, monitoring, load tests, security configs | 8, 9, 10 | DevSecOps |
| [`.github/`](.github/) | CI/CD workflows, CODEOWNERS, templates | 11 | DevSecOps |
| [`docs/`](docs/) | Architecture diagrams, technical reports | — | All |
| [`scripts/`](scripts/) | Developer helper scripts | — | All |

Each top-level folder has its own README describing how to build, test and run it.

## Delivery pipeline (Task 11)

```
Git push → Build → Unit tests → SonarQube → Security scan (secrets, deps, images)
        → Docker build & push → Deploy to Kubernetes → Integration tests → (auto-rollback on failure)
```

## Getting started

```bash
git clone https://github.com/RADAHassan/riskpulse-platform.git
cd riskpulse-platform
```

Then follow the README of the component you work on. Contribution rules (branches, commits, pull
requests) are in [CONTRIBUTING.md](CONTRIBUTING.md); security reporting in [SECURITY.md](SECURITY.md).

## Status

| Component | Status |
| :--- | :--- |
| ML (Tasks 2, 3, 4, 7) | ✅ Done — see [`ml/README.md`](ml/README.md) |
| Backend microservices | ⏳ To do |
| Frontend | ⏳ To do |
| MLflow pipeline & FastAPI serving | ⏳ To do |
| Docker / Kubernetes / HPA | ⏳ To do |
| Prometheus / Grafana / alerts | ⏳ To do |
| Load & HA experiments | ⏳ To do |
| CI/CD & DevSecOps | 🚧 In progress (secret scan, dependency scan, ML CI) |
