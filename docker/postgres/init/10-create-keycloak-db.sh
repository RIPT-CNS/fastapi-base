#!/bin/sh
# Runs once, when the postgres volume is first initialized.
set -e

if [ -n "$KEYCLOAK_DB_NAME" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
SELECT 'CREATE DATABASE "$KEYCLOAK_DB_NAME"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$KEYCLOAK_DB_NAME')\gexec
EOSQL
fi
