"""Create the per-tenant ContextRAG credentials and the shared secrets for the local 3-service stack.

Tenant identity across all layers is the portal's ``tenants.id`` (a UUID), so nothing needs a translation table.

Outputs (in $E2E_DIR, default .e2e):
  contextrag_keys.json   digests only  → ContextRAG   (CONTEXTRAG_KEYS_FILE)
  rag_tenant_keys.json   tenant → READER key → Consensus (RAG_TENANT_KEYS_FILE)
  rag_admin_keys.json    tenant → ADMIN key  → ingest_demo.py only
  tenant_aliases.json    tenant → names that must never leak into OTHER tenants' content
  portal_assertion_secret
Run with the ContextRAG virtualenv (needs `contextrag` + `psycopg`).
"""
import json
import os
import secrets
import sys
from pathlib import Path

import psycopg
from contextrag.api.auth import new_entry

out = Path(os.environ.get("E2E_DIR", ".e2e"))
out.mkdir(parents=True, exist_ok=True)
with psycopg.connect(os.environ["PORTAL_DB_ADMIN_URL"]) as c:
    tenants = c.execute("SELECT id, slug, name FROM tenants ORDER BY slug").fetchall()
if not tenants:
    sys.exit("no tenants in the portal database: run `python -m app.db.seed` first")

store, readers, admins, aliases = {}, {}, {}, {}
for tid, slug, name in tenants:
    rk, rd, re_ = new_entry(f"consensus-{slug}", tid, "reader")
    ak, ad, ae = new_entry(f"ingest-{slug}", tid, "admin")
    store[rd], store[ad] = re_, ae
    readers[tid], admins[tid] = rk, ak
    aliases[tid] = [slug, name]

for name, data in {"contextrag_keys.json": store, "rag_tenant_keys.json": readers, "rag_admin_keys.json": admins, "tenant_aliases.json": aliases}.items():
    p = out / name
    p.write_text(json.dumps(data, indent=2))
    p.chmod(0o600)
secret = out / "portal_assertion_secret"
if not secret.exists():
    secret.write_text(secrets.token_urlsafe(48))
    secret.chmod(0o600)
print(f"wrote credentials for {len(tenants)} tenants into {out}/")
