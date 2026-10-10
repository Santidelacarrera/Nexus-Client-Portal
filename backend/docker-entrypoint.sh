#!/bin/sh
set -e
python -m app.tools.genkeys --dir "${KEYS_DIR:-/keys}"
python -m app.db.bootstrap            # schema + RLS + append-only audit (uses DATABASE_ADMIN_URL)
if [ "${SEED_ON_START:-false}" = "true" ]; then python -m app.db.seed; fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-server-header
