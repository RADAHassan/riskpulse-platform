# Platform contracts

Single source of truth for ports, images, environment variables, endpoints and payload schemas.
Every component (backend, mlops, frontend, infra) **must** conform to this folder.

| File | Content |
| :--- | :--- |
| [`services.md`](services.md) | Ports, images, databases, environment variables, health endpoints |
| [`endpoints.md`](endpoints.md) | Public API (through the gateway) and internal APIs, roles and ownership rules |
| [`metrics.md`](metrics.md) | Prometheus metric names exposed by each component |
| [`predict-request.schema.json`](predict-request.schema.json) | ml-serving `POST /predict` request |
| [`predict-response.schema.json`](predict-response.schema.json) | ml-serving `POST /predict` response |
