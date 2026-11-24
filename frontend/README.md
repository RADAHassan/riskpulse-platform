# Frontend — React dashboard

Analyst dashboard: transactions, risk decisions, prediction uncertainty / human-review queue, and the
PCA / t-SNE / UMAP visualisations produced in `ml/` (Task 7).

## Conventions

- Talks **only** to the API Gateway; base URL from `VITE_API_BASE_URL` (no hard-coded hosts).
- `npm ci && npm run lint && npm test && npm run build` must pass — this is what CI runs.
- Production image: multi-stage `Dockerfile` (build with Node, serve static files with Nginx, non-root).
