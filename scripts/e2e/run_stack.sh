#!/usr/bin/env bash
# Local end-to-end stack: PostgreSQL + Redis (already running) → ContextRAG :8200 → MultiAgent_Consensus :3100 → Portal API :8000
#
#   PORTAL_PY=/path/to/portal/venv/bin/python RAG_PY=/path/to/contextrag/venv/bin/python \
#   CONSENSUS_DIR=../MultiAgent_Consensus PG_ADMIN=postgresql://owner:pw@localhost \
#   scripts/e2e/run_stack.sh start|stop
#
# Requires a PostgreSQL superuser/owner (PG_ADMIN) able to create the roles `nexus_app` and `contextrag_app` (non-superuser).
set -euo pipefail
cd "$(dirname "$0")/../.."
E2E_DIR="${E2E_DIR:-$PWD/.e2e}"; export E2E_DIR
PORTAL_PY="${PORTAL_PY:-python}"; RAG_PY="${RAG_PY:-python}"
CONSENSUS_DIR="${CONSENSUS_DIR:-}"; [ "${1:-start}" = stop ] || : "${CONSENSUS_DIR:?set CONSENSUS_DIR to a checkout of MultiAgent_Consensus (with the answer_gate module)}"
PG_ADMIN="${PG_ADMIN:-}"; [ "${1:-start}" = stop ] || : "${PG_ADMIN:?e.g. postgresql://nexus_owner:owner_pw@localhost}"
PG_NEXUS_APP="${PG_NEXUS_APP:-postgresql+psycopg://nexus_app:app_pw@localhost}"
PG_CRAG_APP="${PG_CRAG_APP:-postgresql://contextrag_app:crag_pw@localhost}"
DEMO_PW="${SEED_DEMO_PASSWORD:-ChangeMe-Nexus-Demo-2025!}"

stop() { for p in "$E2E_DIR"/*.pid; do [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null || true; rm -f "$p"; done; }
wait_http() { for _ in $(seq 1 60); do curl -fsS "$1" >/dev/null 2>&1 && return 0; sleep 1; done; echo "timeout waiting for $1" >&2; exit 1; }

case "${1:-start}" in
  stop) stop; exit 0;;
  start) ;;
  *) echo "usage: $0 start|stop"; exit 2;;
esac
stop; mkdir -p "$E2E_DIR"

# 1) databases ------------------------------------------------------------------------------------------------
psql "$PG_ADMIN/postgres" -qc "DROP DATABASE IF EXISTS nexus_e2e" -c "DROP DATABASE IF EXISTS contextrag_e2e" \
  -c "CREATE DATABASE nexus_e2e" -c "CREATE DATABASE contextrag_e2e"
for role in nexus_app contextrag_app; do
  pw=app_pw; [ "$role" = contextrag_app ] && pw=crag_pw
  psql "$PG_ADMIN/postgres" -qtc "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$role') THEN CREATE ROLE $role LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '$pw'; END IF; END \$\$"
done
export DATABASE_URL="$PG_NEXUS_APP/nexus_e2e" DATABASE_ADMIN_URL="${PG_ADMIN/postgresql:/postgresql+psycopg:}/nexus_e2e"
export ENVIRONMENT=development SEED_DEMO_PASSWORD="$DEMO_PW" CORS_ORIGINS='["http://localhost:3000"]'
(cd backend && "$PORTAL_PY" -m app.db.seed >/dev/null)
PORTAL_DB_ADMIN_URL="$PG_ADMIN/nexus_e2e" "$RAG_PY" scripts/e2e/prepare_keys.py

# 2) ContextRAG (offline stack: hashing embeddings, in-memory index; audit in PostgreSQL as contextrag_app) -----------
env -u DATABASE_URL -u DATABASE_ADMIN_URL POSTGRES_DSN="$PG_CRAG_APP/contextrag_e2e" POSTGRES_ADMIN_DSN="$PG_ADMIN/contextrag_e2e" CONTEXTRAG_KEYS_FILE="$E2E_DIR/contextrag_keys.json" \
  setsid nohup "$RAG_PY" -m uvicorn --factory contextrag.api.server:app_factory --port 8200 >"$E2E_DIR/contextrag.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/rag.pid"
wait_http http://localhost:8200/healthz
RAG_URL=http://localhost:8200 "$RAG_PY" scripts/e2e/ingest_demo.py

# 3) MultiAgent_Consensus (answer gate) ---------------------------------------------------------------------------
# NOTE: every service reads its own DATABASE_URL/REDIS_URL — never leak the portal's into another service.
(cd "$CONSENSUS_DIR" && env -u DATABASE_URL -u DATABASE_ADMIN_URL -u REDIS_URL BUS_BACKEND=memory PORT=3100 PORTAL_ASSERTION_SECRET="$(cat "$E2E_DIR/portal_assertion_secret")" RAG_URL=http://localhost:8200 \
  RAG_TENANT_KEYS_FILE="$E2E_DIR/rag_tenant_keys.json" GATE_TENANT_ALIASES_FILE="$E2E_DIR/tenant_aliases.json" \
  setsid nohup npx ts-node orchestrator/src/main.ts >"$E2E_DIR/consensus.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/consensus.pid")
wait_http http://localhost:3100/health

# 4) Portal API ----------------------------------------------------------------------------------------------------
(cd backend && CONSENSUS_URL=http://localhost:3100 CONSENSUS_ASSERTION_SECRET="$(cat "$E2E_DIR/portal_assertion_secret")" \
  setsid nohup "$PORTAL_PY" -m uvicorn app.main:app --port 8000 >"$E2E_DIR/portal.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/portal.pid")
wait_http http://localhost:8000/health
echo "stack up: portal :8000 · consensus :3100 · contextrag :8200   (demo password: $DEMO_PW)"
