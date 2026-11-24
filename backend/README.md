# Backend — Spring Boot microservices (Task 1)

| Service | Responsibility | Port (local) |
| :--- | :--- | :---: |
| `api-gateway` | Single entry point, routing, JWT validation, rate limiting | 8080 |
| `auth-service` | Users, login, JWT issuing, roles | 8081 |
| `customer-service` | Customer profiles | 8082 |
| `transaction-service` | Transactions intake and history | 8083 |
| `risk-service` | Calls `ml-serving` (FastAPI), applies decision policy / human review routing | 8084 |
| `notification-service` | Alerts to analysts / customers | 8085 |
| `audit-service` | Immutable audit trail of decisions | 8086 |

## Conventions (so DevSecOps can containerise, deploy and monitor every service the same way)

- Java 21, Maven, one Maven module per folder (`backend/<service>/pom.xml`).
- Expose **Spring Boot Actuator**: `/actuator/health/liveness`, `/actuator/health/readiness`, `/actuator/prometheus`
  (dependencies: `spring-boot-starter-actuator`, `micrometer-registry-prometheus`).
- All configuration from environment variables (`SPRING_DATASOURCE_URL`, `JWT_SECRET`, `ML_SERVING_URL`…); no secrets in `application.yml`.
- Each service has a `Dockerfile` in its folder and unit tests runnable with `mvn -B verify`.
