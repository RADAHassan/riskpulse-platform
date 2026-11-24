# Infrastructure — DevSecOps (Tasks 8, 9, 10, 11)

| Folder | Content |
| :--- | :--- |
| `docker/` | `docker-compose.yml` to run the whole platform locally |
| `k8s/base/` | Deployments, Services, Ingress, ConfigMaps, Secrets (templates), probes, resource limits, HPA |
| `k8s/overlays/{dev,prod}/` | Kustomize overlays (replicas, limits, image tags per environment) |
| `monitoring/prometheus/` | Scrape configs and alerting rules |
| `monitoring/grafana/dashboards/` | Dashboards as JSON (system health, microservices, cluster, load/HA, ML inference, uncertainty) |
| `monitoring/alertmanager/` | Alert routing |
| `load-tests/k6/` | Normal → High → Overload → Recovery scenarios, chaos (pod kill) scripts |
| `security/` | Trivy / SonarQube / Gitleaks configuration |

## Alert thresholds (from the project brief)

| Condition | Severity |
| :--- | :--- |
| CPU > 80 % | warning |
| Response time > 2 s | warning |
| Error rate > 5 % | warning |
| ML uncertainty high | route to human review |
| Pod failure | warning |
| Service unavailable | critical |
