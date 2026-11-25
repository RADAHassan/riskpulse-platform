# Fiche de déploiement : `customer-service`

## 1. Caractéristiques générales

| Élément | Valeur | 
| ----- | ----- | 
| **Image Docker** | `fintech/customer-service:0.1.0` | 
| **Port d'écoute** | `8082` | 
| **Base de données** | `customer_db` (PostgreSQL 17) | 
| **Architecture / État** | Sans état (*stateless* — aucune session en mémoire, plusieurs répliques possibles) | 
| **Utilisateur système** | Non-root (`appuser`) | 
| **Mémoire JVM** | `-XX:MaxRAMPercentage=75`  | 

## 2. Variables d'environnement

| Variable | Secret | Valeur par défaut | Rôle / Description | 
| ----- | ----- | ----- | ----- | 
| `SERVER_PORT` | Non | `8082` | Port HTTP d'écoute du service | 
| `DB_URL` | Non | `jdbc:postgresql://localhost:5432/customer_db` | URL JDBC de connexion à PostgreSQL | 
| `DB_USER` | Non | `fintech` | Utilisateur de la base de données | 
| `DB_PASSWORD` | **Oui** | *Aucun*  | Mot de passe de la base de données | 
| `INTERNAL_SERVICE_TOKEN` | **Oui** | *Vide* (refuse tout appel) | Jeton d'authentification pour les routes `/internal/**` | 
| `ACCOUNT_OVERDRAFT_LIMIT` | Non | `500.00` | Plafond de découvert autorisé pour les comptes courants | 
| `ACCOUNT_SAVINGS_RATE` | Non | `0.0350` | Taux d'intérêt annuel des comptes épargne | 
| `ACCOUNT_SAVINGS_MIN_BALANCE` | Non | `100.00` | Solde minimum requis sur un compte épargne | 
| `SWAGGER_ENABLED` | Non | `true` | Activation de l'interface Swagger UI *(à passer à `false` en production)* | 

## 3. Observabilité (Santé, Métriques et Journaux)

* **Sonde de vivacité (*Liveness*) :** `GET /actuator/health/liveness`

* **Sonde de disponibilité (*Readiness*) :** `GET /actuator/health/readiness`

* **Métriques Prometheus :** `GET /actuator/prometheus`

* **Journaux (*Logs*) :** Écrits sur la sortie standard (`stdout`), incluant l'en-tête de traçabilité `X-Correlation-Id` sur chaque ligne.

## 4. Sécurité et Réseau

* **Endpoints publics (`/api/v1/**`) :** Exposés uniquement via l'API Gateway.

* **Endpoints internes (`/internal/**`) :** Jamais routés par le Gateway ; accès restreint aux microservices autorisés (via `NetworkPolicy`) avec authentification obligatoire par en-tête `X-Service-Token`.

* **En-têtes utilisateur (`X-User-*`) :** L'API Gateway doit impérativement supprimer tout en-tête `X-User-*` envoyé par un client externe avant d'injecter les siens.

## 5. Migrations de base de données

* **Outil :** Flyway s'exécute automatiquement au démarrage de l'application (`V1`, `V2`, etc.).

* **Concurrence :** En cas de démarrage simultané de plusieurs répliques, le mécanisme de verrouillage natif de Flyway garantit qu'une seule réplique applique les migrations.