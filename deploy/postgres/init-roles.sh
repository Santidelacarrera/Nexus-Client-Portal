#!/bin/sh
# Runs once on first volume init. POSTGRES_USER (owner) runs migrations; the app connects as
# nexus_app: NOSUPERUSER + NOBYPASSRLS, so PostgreSQL Row-Level Security always applies to it.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE nexus_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '${NEXUS_APP_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO nexus_app;
SQL
