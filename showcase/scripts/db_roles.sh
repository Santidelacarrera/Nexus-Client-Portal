#!/usr/bin/env bash
# Convierte los roles de schema.sql en roles de LOGIN. Las contraseñas vienen del entorno, nunca del repositorio.
#   ADMIN_URL=postgresql://owner@host/db  APP_DB_PASSWORD=...  STAFF_DB_PASSWORD=...  ./scripts/db_roles.sh
set -euo pipefail
: "${ADMIN_URL:?ADMIN_URL requerida (rol propietario)}" "${APP_DB_PASSWORD:?}" "${STAFF_DB_PASSWORD:?}"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -v app_pw="$APP_DB_PASSWORD" -v staff_pw="$STAFF_DB_PASSWORD" <<'SQL'
ALTER ROLE showcase_app   LOGIN PASSWORD :'app_pw'   NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
ALTER ROLE showcase_staff LOGIN PASSWORD :'staff_pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
SQL
echo "roles listos"
