#!/bin/sh
# One PostgreSQL instance, one database + one dedicated role per service (least privilege).
# Passwords come from the environment (never from the image). Runs once, on first start of the data volume.
set -eu

create_db() {
  db="$1"; password="$2"
  [ -n "$password" ] || { echo "missing password for $db" >&2; exit 1; }
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE ${db}_user LOGIN PASSWORD '${password}';
CREATE DATABASE ${db} OWNER ${db}_user;
REVOKE ALL ON DATABASE ${db} FROM PUBLIC;
GRANT ALL ON DATABASE ${db} TO ${db}_user;
SQL
}

create_db auth         "$POSTGRES_AUTH_PASSWORD"
create_db customer     "$POSTGRES_CUSTOMER_PASSWORD"
create_db transaction  "$POSTGRES_TRANSACTION_PASSWORD"
create_db risk         "$POSTGRES_RISK_PASSWORD"
create_db notification "$POSTGRES_NOTIFICATION_PASSWORD"
create_db audit        "$POSTGRES_AUDIT_PASSWORD"
create_db mlflow       "$POSTGRES_MLFLOW_PASSWORD"

# Read-only monitoring role for postgres-exporter
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE exporter LOGIN PASSWORD '${POSTGRES_EXPORTER_PASSWORD}';
GRANT pg_monitor TO exporter;
SQL
