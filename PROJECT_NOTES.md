# CLAUDE.md — RiskPulse platform (état de reprise)

> Lis ce fichier en premier. Il permet de reprendre le projet dans une nouvelle session.

## Contexte

Projet « High-Availability MLOps FinTech Platform Using Microservices, Kubernetes, Statistical ML Benchmarking
and Intelligent Monitoring ». Repo `RADAHassan/riskpulse-platform`. Deadline **10/01/2027**.
Livrables : repo GitHub, **README = rapport complet**, démo vidéo ≤ 5 min.
Rôle de Hassan : **DevSecOps** (partie évaluée en premier → exemplaire, démontrable, documentée).
Poste : Windows 11, PowerShell, ~16 Go RAM. Scripts locaux `scripts/*.ps1`, scripts CI `scripts/*.sh`.
Réponses à l'utilisateur en français ; code, commits, fichiers, README en anglais.

## Règles de travail

1. Autonomie totale : pas de questions. Choix ambigu → option simple/standard, noter dans « Décisions ».
   Bloqué → livrer le code, valider au maximum, noter dans « À faire par Hassan », continuer.
2. Branche unique `feat/full-platform` (depuis `chore/monorepo-structure`), Conventional Commits
   (scopes : backend, auth-service, frontend, ml, mlops, k8s, monitoring, ci, security, docs…).
   `git push` après chaque phase. Jamais de push sur `main`. PR finale via `gh pr create`.
3. Tout est vérifié en l'exécutant (mvn verify, npm, pytest, docker compose, kubeconform, kube-linter,
   promtool, actionlint, kyverno test, vrais curl / kubectl). Jamais « ça devrait marcher ».
4. ML : aucun résultat chiffré modifié. Les chiffres du rapport viennent de `ml/artifacts/*` et `ml/README.md`.
5. Sécurité par défaut : non-root, readOnlyRootFilesystem, no privilege escalation, drop ALL caps,
   seccomp RuntimeDefault, aucun secret en clair, actions épinglées par SHA, images par digest.
6. Sobriété mémoire : JVM `-XX:MaxRAMPercentage=75`, ~512 Mi par service Spring, 1 PostgreSQL / 1 base par service,
   1 réplica en local, réplicas + HPA dans les overlays K8s. Falco désactivé par défaut.
7. Pas de service mesh, pas d'ArgoCD, pas de Kafka.

## Architecture (décisions de contrat → `docs/contracts/`)

- Flux : `POST /api/transactions` → gateway (JWT) → transaction-service → risk-service → ml-serving `/predict`
  → décision `APPROVE | HUMAN_REVIEW | DECLINE` → audit-service + notification-service (REVIEW/DECLINE).
- Une prédiction incertaine n'est **jamais** auto-déclinée. Fallback ml-serving KO ⇒ `HUMAN_REVIEW`, jamais `APPROVE`.
- JWT RS256 (clé privée dans auth-service, JWKS public), access 15 min + refresh rotatif.
- Appels internes `/internal/**` : JWT propagé **et** en-tête `X-Service-Key`. ml-serving : `X-Service-Key`.

## Plan et avancement

| Phase | Contenu | État |
| :-- | :-- | :-- |
| 0 | Fondations : outils, CLAUDE.md, contrats, pre-commit, gitleaks | ⏳ |
| 1 | Correction ML + packaging (autoencoder, torch, tests) | ⏳ |
| 2 | MLOps / MLflow pipeline | ⏳ |
| 3 | Serving FastAPI | ⏳ |
| 4 | Backend Spring Boot (7 modules) | ⏳ |
| 5 | Frontend React | ⏳ |
| 6 | Stack Docker Compose + e2e | ⏳ |
| 7 | Kubernetes (kind, kustomize, HPA, rollback) | ⏳ |
| 8 | Observabilité (Prometheus, Grafana, alertes) | ⏳ |
| 9 | CI/CD sécurisé | ⏳ |
| 10 | Sécurité cluster/runtime (PSA, RBAC, NetPol, Kyverno, Sealed Secrets, Trivy Operator) | ⏳ |
| 11 | Charge & HA (k6, chaos) | ⏳ |
| 12 | Preuves DevSecOps (STRIDE, matrice, gate-evidence) | ⏳ |
| 13 | Rapport final, runbook, script de démo | ⏳ |

## Décisions

- Local Python 3.12 (venv `ml/.venv`, ignoré par git) ; CI ML existante utilise 3.14.
- Maven non disponible via winget → téléchargé dans `~/tools` (voir `scripts/`), puis Maven Wrapper (`mvnw`) dans `backend/`.

## À faire par Hassan

(rempli au fil de l'eau)

## Journal des blocages

(rempli au fil de l'eau)
