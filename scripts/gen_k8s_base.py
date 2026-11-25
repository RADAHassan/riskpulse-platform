"""Render infra/k8s/base from a compact workload table (committed output; run after changing a workload).

    python scripts/gen_k8s_base.py

Every workload gets the same hardening: non-root, read-only root filesystem, no privilege escalation,
all capabilities dropped, seccomp RuntimeDefault, dedicated ServiceAccount without API token,
startup/liveness/readiness probes, requests/limits, RollingUpdate with maxUnavailable 0, topology spread,
PodDisruptionBudget and an HPA (CPU 70 %, 2..6).
"""

from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "infra" / "k8s" / "base"
REGISTRY = "ghcr.io/radahassan"
NS = "riskpulse"

PG_SERVICES = {"auth": "auth", "customer": "customer", "transaction": "transaction", "risk": "risk",
               "notification": "notification", "audit": "audit"}


def spring(name, port, db=None, extra_env=None):
    return {"name": name, "port": port, "kind": "spring", "db": db, "env": extra_env or {},
            "cpu_req": "250m", "cpu_lim": "1", "mem_req": "384Mi", "mem_lim": "512Mi",
            "live": "/actuator/health/liveness", "ready": "/actuator/health/readiness", "user": 10001}


WORKLOADS = [
    spring("api-gateway", 8080, extra_env={
        "CORS_ALLOWED_ORIGINS": ("cfg", "CORS_ALLOWED_ORIGINS"), "TRUST_FORWARDED_FOR": ("cfg", "TRUST_FORWARDED_FOR"),
        "RATE_LIMIT_IP_PER_MIN": ("cfg", "RATE_LIMIT_IP_PER_MIN"), "RATE_LIMIT_USER_PER_MIN": ("cfg", "RATE_LIMIT_USER_PER_MIN"),
        "AUTH_SERVICE_URL": ("cfg", "AUTH_SERVICE_URL"), "CUSTOMER_SERVICE_URL": ("cfg", "CUSTOMER_SERVICE_URL"),
        "TRANSACTION_SERVICE_URL": ("cfg", "TRANSACTION_SERVICE_URL"), "RISK_SERVICE_URL": ("cfg", "RISK_SERVICE_URL"),
        "NOTIFICATION_SERVICE_URL": ("cfg", "NOTIFICATION_SERVICE_URL"), "AUDIT_SERVICE_URL": ("cfg", "AUDIT_SERVICE_URL"),
        "ML_SERVING_URL": ("cfg", "ML_SERVING_URL")}),
    spring("auth-service", 8081, "auth", {
        "JWT_PRIVATE_KEY": ("sec", "JWT_PRIVATE_KEY"), "JWT_PUBLIC_KEY": ("sec", "JWT_PUBLIC_KEY"),
        "JWT_KEY_ID": ("cfg", "JWT_KEY_ID"), "SEED_ADMIN_PASSWORD": ("sec", "SEED_ADMIN_PASSWORD"),
        "SEED_ANALYST_PASSWORD": ("sec", "SEED_ANALYST_PASSWORD")}),
    spring("customer-service", 8082, "customer"),
    spring("transaction-service", 8083, "transaction", {"RISK_SERVICE_URL": ("cfg", "RISK_SERVICE_URL")}),
    spring("risk-service", 8084, "risk", {
        "ML_SERVING_URL": ("cfg", "ML_SERVING_URL"), "NOTIFICATION_SERVICE_URL": ("cfg", "NOTIFICATION_SERVICE_URL"),
        "TRANSACTION_SERVICE_URL": ("cfg", "TRANSACTION_SERVICE_URL")}),
    spring("notification-service", 8085, "notification"),
    spring("audit-service", 8086, "audit"),
    {"name": "ml-serving", "port": 8000, "kind": "python", "db": None, "user": 10001,
     "env": {"MLFLOW_TRACKING_URI": ("cfg", "MLFLOW_TRACKING_URI"), "MODEL_URI": ("cfg", "MODEL_URI"),
             "MLFLOW_HTTP_REQUEST_TIMEOUT": ("lit", "10"), "MLFLOW_HTTP_REQUEST_MAX_RETRIES": ("lit", "1")},
     "cpu_req": "500m", "cpu_lim": "2", "mem_req": "768Mi", "mem_lim": "1280Mi",
     "live": "/health/live", "ready": "/health/ready", "startup_failures": 40},
    {"name": "frontend", "port": 8080, "kind": "nginx", "db": None, "user": 101, "env": {},
     "cpu_req": "50m", "cpu_lim": "250m", "mem_req": "32Mi", "mem_lim": "96Mi",
     "live": "/healthz", "ready": "/healthz"},
]


def env_block(w: dict) -> str:
    lines = []
    if w["kind"] == "spring":
        lines += ["- name: JAVA_TOOL_OPTIONS", "  valueFrom: { configMapKeyRef: { name: riskpulse-config, key: JAVA_TOOL_OPTIONS } }",
                  "- name: SERVER_PORT", f"  value: \"{w['port']}\"",
                  "- name: JWT_ISSUER", "  valueFrom: { configMapKeyRef: { name: riskpulse-config, key: JWT_ISSUER } }",
                  "- name: JWT_JWKS_URI", "  valueFrom: { configMapKeyRef: { name: riskpulse-config, key: JWT_JWKS_URI } }",
                  "- name: AUDIT_SERVICE_URL", "  valueFrom: { configMapKeyRef: { name: riskpulse-config, key: AUDIT_SERVICE_URL } }"]
    if w["kind"] in ("spring", "python"):
        lines += ["- name: SERVICE_KEY", "  valueFrom: { secretKeyRef: { name: riskpulse-secrets, key: SERVICE_KEY } }"]
    if w["db"]:
        db = w["db"]
        lines += ["- name: SPRING_DATASOURCE_URL", f"  value: jdbc:postgresql://postgres:5432/{db}",
                  "- name: SPRING_DATASOURCE_USERNAME", f"  value: {db}_user",
                  "- name: SPRING_DATASOURCE_PASSWORD",
                  f"  valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_{db.upper()}_PASSWORD }} }}"]
    for key, (src, ref) in w["env"].items():
        if key in ("JAVA_TOOL_OPTIONS", "SERVICE_KEY"):
            continue
        lines.append(f"- name: {key}")
        if src == "cfg":
            lines.append(f"  valueFrom: {{ configMapKeyRef: {{ name: riskpulse-config, key: {ref} }} }}")
        elif src == "sec":
            lines.append(f"  valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: {ref} }} }}")
        else:
            lines.append(f"  value: \"{ref}\"")
    if w["kind"] == "python":
        lines += ["- name: HOME", "  value: /tmp", "- name: MPLCONFIGDIR", "  value: /tmp"]
    return "\n".join("            " + line for line in lines)


def workload_yaml(w: dict) -> str:
    n, port = w["name"], w["port"]
    startup_failures = w.get("startup_failures", 30)
    env = env_block(w)
    return f"""# GENERATED by scripts/gen_k8s_base.py — do not edit by hand.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {n}
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: {n}, app.kubernetes.io/part-of: riskpulse }}
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {n}
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: {n}, app.kubernetes.io/part-of: riskpulse }}
spec:
  replicas: 2
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 420
  minReadySeconds: 5
  strategy:
    type: RollingUpdate
    rollingUpdate: {{ maxUnavailable: 0, maxSurge: 1 }}
  selector:
    matchLabels: {{ app.kubernetes.io/name: {n} }}
  template:
    metadata:
      labels: {{ app.kubernetes.io/name: {n}, app.kubernetes.io/part-of: riskpulse, app: {n} }}
      annotations:
        prometheus.io/scrape: "true"
    spec:
      serviceAccountName: {n}
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      securityContext:
        runAsNonRoot: true
        runAsUser: {w['user']}
        runAsGroup: {w['user']}
        fsGroup: {w['user']}
        seccompProfile: {{ type: RuntimeDefault }}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels: {{ app.kubernetes.io/name: {n} }}
      containers:
        - name: {n}
          image: {REGISTRY}/riskpulse-{n}:0.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - {{ name: http, containerPort: {port} }}
          env:
{env}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            capabilities: {{ drop: [ALL] }}
            seccompProfile: {{ type: RuntimeDefault }}
          resources:
            requests: {{ cpu: {w['cpu_req']}, memory: {w['mem_req']} }}
            limits: {{ cpu: "{w['cpu_lim']}", memory: {w['mem_lim']} }}
          startupProbe:
            httpGet: {{ path: {w['ready']}, port: http }}
            periodSeconds: 5
            failureThreshold: {startup_failures}
            timeoutSeconds: 3
          livenessProbe:
            httpGet: {{ path: {w['live']}, port: http }}
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          readinessProbe:
            httpGet: {{ path: {w['ready']}, port: http }}
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          lifecycle:
            preStop:
              exec: {{ command: ["sleep", "5"] }}
          volumeMounts:
            - {{ name: tmp, mountPath: /tmp }}
      volumes:
        - name: tmp
          emptyDir: {{ sizeLimit: 256Mi }}
---
apiVersion: v1
kind: Service
metadata:
  name: {n}
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: {n}, app.kubernetes.io/part-of: riskpulse }}
spec:
  selector: {{ app.kubernetes.io/name: {n} }}
  ports:
    - {{ name: http, port: {port}, targetPort: http }}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {n}
  namespace: {NS}
spec:
  scaleTargetRef: {{ apiVersion: apps/v1, kind: Deployment, name: {n} }}
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: {{ type: Utilization, averageUtilization: 70 }}
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - {{ type: Pods, value: 2, periodSeconds: 30 }}
    scaleDown:
      stabilizationWindowSeconds: 120
      policies:
        - {{ type: Pods, value: 1, periodSeconds: 60 }}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {n}
  namespace: {NS}
spec:
  maxUnavailable: 1
  selector:
    matchLabels: {{ app.kubernetes.io/name: {n} }}
"""


NAMESPACE = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {NS}
  labels:
    app.kubernetes.io/part-of: riskpulse
    # Pod Security Admission: the whole namespace must satisfy the "restricted" profile
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
"""

CONFIG = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: riskpulse-config
  namespace: {NS}
  labels: {{ app.kubernetes.io/part-of: riskpulse }}
data:
  JAVA_TOOL_OPTIONS: "-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError -Djava.security.egd=file:/dev/./urandom"
  JWT_ISSUER: riskpulse-auth
  JWT_KEY_ID: rp-k8s-1
  JWT_JWKS_URI: http://auth-service:8081/.well-known/jwks.json
  AUDIT_SERVICE_URL: http://audit-service:8086
  AUTH_SERVICE_URL: http://auth-service:8081
  CUSTOMER_SERVICE_URL: http://customer-service:8082
  TRANSACTION_SERVICE_URL: http://transaction-service:8083
  RISK_SERVICE_URL: http://risk-service:8084
  NOTIFICATION_SERVICE_URL: http://notification-service:8085
  ML_SERVING_URL: http://ml-serving:8000
  CORS_ALLOWED_ORIGINS: http://riskpulse.localtest.me:8088
  TRUST_FORWARDED_FOR: "true"
  RATE_LIMIT_IP_PER_MIN: "300"
  RATE_LIMIT_USER_PER_MIN: "600"
  MLFLOW_TRACKING_URI: http://mlflow:5000
  MODEL_URI: models:/riskpulse-fraud@champion
"""

QUOTA = f"""apiVersion: v1
kind: LimitRange
metadata:
  name: defaults
  namespace: {NS}
spec:
  limits:
    - type: Container
      default: {{ cpu: 500m, memory: 512Mi }}
      defaultRequest: {{ cpu: 100m, memory: 128Mi }}
      max: {{ cpu: "2", memory: 2Gi }}
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute
  namespace: {NS}
spec:
  hard:
    requests.cpu: "16"
    requests.memory: 16Gi
    limits.cpu: "32"
    limits.memory: 32Gi
    pods: "80"
    persistentvolumeclaims: "6"
"""

INGRESS = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: riskpulse
  namespace: {NS}
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: 1m
    nginx.ingress.kubernetes.io/proxy-read-timeout: "30"
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
    nginx.ingress.kubernetes.io/limit-rps: "200"
    nginx.ingress.kubernetes.io/server-snippet: |
      server_tokens off;
spec:
  ingressClassName: nginx
  rules:
    - host: riskpulse.localtest.me
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: {{ name: frontend, port: {{ number: 8080 }} }}
"""

POSTGRES = f"""apiVersion: v1
kind: ServiceAccount
metadata: {{ name: postgres, namespace: {NS} }}
automountServiceAccountToken: false
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: postgres, app.kubernetes.io/part-of: riskpulse }}
spec:
  clusterIP: None
  selector: {{ app.kubernetes.io/name: postgres }}
  ports:
    - {{ name: postgres, port: 5432, targetPort: postgres }}
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: postgres, app.kubernetes.io/part-of: riskpulse }}
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels: {{ app.kubernetes.io/name: postgres }}
  template:
    metadata:
      labels: {{ app.kubernetes.io/name: postgres, app.kubernetes.io/part-of: riskpulse, app: postgres }}
    spec:
      serviceAccountName: postgres
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 70
        runAsGroup: 70
        fsGroup: 70
        seccompProfile: {{ type: RuntimeDefault }}
      containers:
        - name: postgres
          image: postgres:17-alpine@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73
          imagePullPolicy: IfNotPresent
          ports:
            - {{ name: postgres, containerPort: 5432 }}
          env:
            - {{ name: PGDATA, value: /var/lib/postgresql/data/pgdata }}
            - {{ name: POSTGRES_USER, value: postgres }}
            - name: POSTGRES_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_PASSWORD }} }}
            - name: POSTGRES_AUTH_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_AUTH_PASSWORD }} }}
            - name: POSTGRES_CUSTOMER_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_CUSTOMER_PASSWORD }} }}
            - name: POSTGRES_TRANSACTION_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_TRANSACTION_PASSWORD }} }}
            - name: POSTGRES_RISK_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_RISK_PASSWORD }} }}
            - name: POSTGRES_NOTIFICATION_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_NOTIFICATION_PASSWORD }} }}
            - name: POSTGRES_AUDIT_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_AUDIT_PASSWORD }} }}
            - name: POSTGRES_MLFLOW_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_MLFLOW_PASSWORD }} }}
            - name: POSTGRES_EXPORTER_PASSWORD
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: POSTGRES_EXPORTER_PASSWORD }} }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            capabilities: {{ drop: [ALL] }}
            seccompProfile: {{ type: RuntimeDefault }}
          resources:
            requests: {{ cpu: 100m, memory: 256Mi }}
            limits: {{ cpu: "1", memory: 512Mi }}
          startupProbe:
            exec: {{ command: ["pg_isready", "-U", "postgres"] }}
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            exec: {{ command: ["pg_isready", "-U", "postgres"] }}
            periodSeconds: 10
            failureThreshold: 6
          readinessProbe:
            exec: {{ command: ["pg_isready", "-U", "postgres"] }}
            periodSeconds: 5
            failureThreshold: 3
          volumeMounts:
            - {{ name: data, mountPath: /var/lib/postgresql/data }}
            - {{ name: init, mountPath: /docker-entrypoint-initdb.d, readOnly: true }}
            - {{ name: tmp, mountPath: /tmp }}
            - {{ name: run, mountPath: /var/run/postgresql }}
      volumes:
        - name: init
          configMap: {{ name: postgres-init, defaultMode: 0555 }}
        - name: tmp
          emptyDir: {{ sizeLimit: 128Mi }}
        - name: run
          emptyDir: {{ sizeLimit: 8Mi }}
  volumeClaimTemplates:
    - metadata: {{ name: data }}
      spec:
        accessModes: [ReadWriteOnce]
        resources: {{ requests: {{ storage: 2Gi }} }}
"""

MLFLOW = f"""apiVersion: v1
kind: ServiceAccount
metadata: {{ name: mlflow, namespace: {NS} }}
automountServiceAccountToken: false
---
apiVersion: v1
kind: Service
metadata:
  name: mlflow
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: mlflow, app.kubernetes.io/part-of: riskpulse }}
spec:
  selector: {{ app.kubernetes.io/name: mlflow }}
  ports:
    - {{ name: http, port: 5000, targetPort: http }}
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mlflow
  namespace: {NS}
  labels: {{ app.kubernetes.io/name: mlflow, app.kubernetes.io/part-of: riskpulse }}
spec:
  serviceName: mlflow
  replicas: 1
  selector:
    matchLabels: {{ app.kubernetes.io/name: mlflow }}
  template:
    metadata:
      labels: {{ app.kubernetes.io/name: mlflow, app.kubernetes.io/part-of: riskpulse, app: mlflow }}
    spec:
      serviceAccountName: mlflow
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {{ type: RuntimeDefault }}
      containers:
        - name: mlflow
          image: {REGISTRY}/riskpulse-mlflow:0.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - {{ name: http, containerPort: 5000 }}
          env:
            - name: MLFLOW_BACKEND_STORE_URI
              valueFrom: {{ secretKeyRef: {{ name: riskpulse-secrets, key: MLFLOW_BACKEND_STORE_URI }} }}
            - {{ name: MLFLOW_ALLOWED_HOSTS, value: "mlflow:5000,mlflow.riskpulse.svc:5000,mlflow.riskpulse.svc.cluster.local:5000,localhost:5000,127.0.0.1:5000,*:5000" }}
            - {{ name: HOME, value: /tmp }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            capabilities: {{ drop: [ALL] }}
            seccompProfile: {{ type: RuntimeDefault }}
          resources:
            requests: {{ cpu: 100m, memory: 256Mi }}
            limits: {{ cpu: "1", memory: 640Mi }}
          startupProbe:
            httpGet: {{ path: /health, port: http, httpHeaders: [{{ name: Host, value: "mlflow:5000" }}] }}
            periodSeconds: 5
            failureThreshold: 40
          livenessProbe:
            httpGet: {{ path: /health, port: http, httpHeaders: [{{ name: Host, value: "mlflow:5000" }}] }}
            periodSeconds: 15
            failureThreshold: 4
          readinessProbe:
            httpGet: {{ path: /health, port: http, httpHeaders: [{{ name: Host, value: "mlflow:5000" }}] }}
            periodSeconds: 10
            failureThreshold: 3
          volumeMounts:
            - {{ name: artifacts, mountPath: /mlartifacts }}
            - {{ name: tmp, mountPath: /tmp }}
      volumes:
        - name: tmp
          emptyDir: {{ sizeLimit: 128Mi }}
  volumeClaimTemplates:
    - metadata: {{ name: artifacts }}
      spec:
        accessModes: [ReadWriteOnce]
        resources: {{ requests: {{ storage: 1Gi }} }}
"""


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    for old in BASE.glob("*.yaml"):
        old.unlink()
    resources = ["namespace.yaml", "config.yaml", "quota.yaml"]
    (BASE / "namespace.yaml").write_text(NAMESPACE, encoding="utf-8")
    (BASE / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (BASE / "quota.yaml").write_text(QUOTA, encoding="utf-8")
    (BASE / "postgres.yaml").write_text(POSTGRES, encoding="utf-8")
    (BASE / "mlflow.yaml").write_text(MLFLOW, encoding="utf-8")
    (BASE / "ingress.yaml").write_text(INGRESS, encoding="utf-8")
    resources += ["postgres.yaml", "mlflow.yaml"]
    for w in WORKLOADS:
        (BASE / f"{w['name']}.yaml").write_text(workload_yaml(w), encoding="utf-8")
        resources.append(f"{w['name']}.yaml")
    resources.append("ingress.yaml")
    kustomization = (
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nnamespace: riskpulse\n\nresources:\n"
        + "".join(f"  - {r}\n" for r in resources)
        + "\nconfigMapGenerator:\n  - name: postgres-init\n    files:\n      - init-databases.sh=init-databases.sh\n"
          "    options:\n      disableNameSuffixHash: true\n"
    )
    # kustomize cannot read files outside the kustomization directory: keep a copy of the init script next to it
    shutil.copyfile(BASE.parents[1] / "docker" / "postgres" / "init-databases.sh", BASE / "init-databases.sh")
    (BASE / "kustomization.yaml").write_text(kustomization, encoding="utf-8")
    print(f"wrote {len(resources)} resources to {BASE}")


if __name__ == "__main__":
    main()
