"""End-to-end scenarios against the REAL stack (portal → consensus → ContextRAG → PostgreSQL RLS).

    python scripts/e2e/verify_flow.py          (portal venv; stack started by run_stack.sh)

Exits non-zero on the first violated expectation. This is the executable acceptance test for the integration.
"""
import json
import os
import sys
from pathlib import Path

import httpx
import psycopg

PORTAL, RAG, GATE = "http://localhost:8000", "http://localhost:8200", "http://localhost:3100"
PW = os.environ.get("SEED_DEMO_PASSWORD", "ChangeMe-Nexus-Demo-2025!")
E2E = Path(os.environ.get("E2E_DIR", ".e2e"))
keys = json.loads((E2E / "rag_tenant_keys.json").read_text())
aliases = json.loads((E2E / "tenant_aliases.json").read_text())
tid = {a[0]: t for t, a in aliases.items()}
http = httpx.Client(timeout=60)
passed = 0


def check(name, cond, extra=""):
    global passed
    print(("  ✓ " if cond else "  ✘ ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        sys.exit(f"FAILED: {name}")
    passed += 1


def login(email):
    r = http.post(f"{PORTAL}/api/v1/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ask(h, q):
    r = http.post(f"{PORTAL}/api/v1/ask", json={"question": q}, headers=h)
    return r, (r.json().get("review") if r.status_code == 200 else None)


acme, helix = login("ciso@acme-fintech.example"), login("ciso@helix-health.example")
codes = lambda rv: {x["code"] for x in rv["reasons"]}  # noqa: E731

print("1. unanimous release, each tenant gets its OWN knowledge")
r, rv = ask(acme, "¿Cuánto tiempo se conservan los registros de auditoría?")
check("acme: RELEASED with the 7-year answer", r.status_code == 200 and rv["outcome"] == "RELEASED" and "7 años" in rv["answer"], r.text[:300])
check("acme: three approvals and cited sources", [v["vote"] for v in rv["votes"]] == ["approve"] * 3 and rv["sources"][0]["docId"] == "politica_retencion.md")
check("acme: review is bound to acme", rv["tenantId"] == tid["acme-fintech"])
r, rv = ask(helix, "¿Cuánto tiempo se conservan las historias clínicas?")
check("helix: RELEASED with the 15-year answer", rv["outcome"] == "RELEASED" and "15 años" in rv["answer"], r.text[:300])

print("2. tenant isolation: nobody can reach the other tenant's documents")
leaks = []
for who, h, q, forbidden in [("acme", acme, "¿Cuánto tiempo se conservan las historias clínicas?", ["15 años", "historias_clinicas"]),
                             ("helix", helix, "¿Cuánto tiempo se conservan los registros de auditoría?", ["7 años", "politica_retencion"])]:
    r, rv = ask(h, q)
    blob = r.text
    leaks += [f for f in forbidden if f in blob]
    check(f"{who}: asking about the other tenant's topic returns nothing of it (outcome={rv['outcome']})", not [f for f in forbidden if f in blob], blob[:300])

print("3. hostile content is vetoed (fail-closed): no answer, no sources")
r, rv = ask(acme, "¿Cuántos días de vacaciones tiene el personal?")
check("prompt injection inside a document → BLOCKED + security veto", rv["outcome"] == "BLOCKED" and "tenant_security_veto" in codes(rv) and "prompt_injection" in codes(rv), r.text[:400])
check("…answer withheld and sources hidden", rv["answer"] is None and rv["sources"] == [] and "90 days" not in r.text)
r, rv = ask(acme, "¿Quién emite las facturas de facturación mensual a los socios?")
check("another tenant's name inside a document → BLOCKED + foreign_tenant_reference", rv["outcome"] == "BLOCKED" and "foreign_tenant_reference" in codes(rv), r.text[:400])
check("…answer withheld and sources hidden", rv["answer"] is None and rv["sources"] == [])

print("4. committee disagreement / no context never yields an answer")
r, rv = ask(acme, "zzzz qwerty xyzzy plugh")
check("gibberish → BLOCKED, no answer", rv["outcome"] == "BLOCKED" and rv["answer"] is None, r.text[:300])
r, rv = ask(acme, "¿Cuál es el horario de soporte?")
check("support hours → RELEASED (control: clean docs are not blocked)", rv["outcome"] == "RELEASED" and "9:00" in rv["answer"], r.text[:300])

print("5. portal API cannot be steered")
check("body tenant_id is rejected (422)", http.post(f"{PORTAL}/api/v1/ask", json={"question": "¿hola mundo?", "tenant_id": tid["helix-health"]}, headers=acme).status_code == 422)
check("anonymous → 401", http.post(f"{PORTAL}/api/v1/ask", json={"question": "¿hola mundo?"}).status_code == 401)
runs = http.get(f"{PORTAL}/api/v1/ask", headers=acme).json()
helix_runs = http.get(f"{PORTAL}/api/v1/ask", headers=helix).json()
check("acme and helix histories are disjoint and non-empty", runs and helix_runs and not ({x["runId"] for x in runs} & {x["runId"] for x in helix_runs}))
rid = runs[0]["runId"]
check("helix cannot open acme's run (404)", http.get(f"{PORTAL}/api/v1/ask/{rid}", headers=helix).status_code == 404)

print("6. the layers below refuse to be bypassed")
check("consensus rejects calls without the portal's signed assertion", http.post(f"{GATE}/v1/answer-gate/reviews", json={"question": "¿hola mundo?"}).status_code == 401)
check("consensus rejects an API key sent as assertion", http.post(f"{GATE}/v1/answer-gate/reviews", json={"question": "¿hola mundo?"}, headers={"x-nexus-assertion": keys[tid["acme-fintech"]]}).status_code == 401)
r = http.post(f"{RAG}/api/v1/retrieve", json={"tenant_id": tid["helix-health"], "query": "historias clínicas"}, headers={"x-api-key": keys[tid["acme-fintech"]]})
check("ContextRAG: acme's key cannot retrieve with helix's tenant_id (403)", r.status_code == 403, r.text[:200])
r = http.post(f"{RAG}/api/v1/retrieve", json={"tenant_id": tid["acme-fintech"], "query": "historias clínicas", "top_k": 5}, headers={"x-api-key": keys[tid["acme-fintech"]]})
check("ContextRAG: acme's own retrieval contains no helix document", r.status_code == 200 and all(f["doc_id"] in ("politica_retencion.md", "soporte.md", "onboarding_notes.md", "partners.md") for f in r.json()["fragments"]))

print("7. PostgreSQL row-level security (as the unprivileged app role contextrag_app)")
with psycopg.connect(os.environ.get("CRAG_APP_DSN", "postgresql://contextrag_app:crag_pw@localhost/contextrag_e2e")) as c:
    me = c.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()
    check(f"role {me[0]} is neither superuser nor BYPASSRLS", me[1] is False and me[2] is False)
    check("with no tenant set the audit table is invisible (fail-closed)", c.execute("SELECT count(*) FROM retrieval_audit").fetchone()[0] == 0)
    with c.transaction():
        c.execute("SELECT set_config('app.tenant', %s, true)", (tid["acme-fintech"],))
        rows = c.execute("SELECT DISTINCT tenant FROM retrieval_audit").fetchall()
        check("with app.tenant=acme only acme's audit rows are visible", rows == [(tid["acme-fintech"],)], str(rows))
    with c.transaction():
        c.execute("SELECT set_config('app.tenant', %s, true)", (tid["helix-health"],))
        check("with app.tenant=helix only helix's rows are visible", c.execute("SELECT DISTINCT tenant FROM retrieval_audit").fetchall() == [(tid["helix-health"],)])
    try:
        with c.transaction():
            c.execute("SELECT set_config('app.tenant', %s, true)", (tid["acme-fintech"],))
            c.execute("DELETE FROM retrieval_audit")
        deleted = True
    except psycopg.errors.InsufficientPrivilege:
        deleted = False
    check("the application role cannot DELETE audit rows (append-only)", not deleted)

print("8. portal audit trail")
v = http.get(f"{PORTAL}/api/v1/audit/verify", headers=acme).json()
check("hash chain intact", v["valid"] is True)
actions = {e["action"] for e in http.get(f"{PORTAL}/api/v1/audit?limit=200", headers=acme).json()}
check("released/blocked questions are audited without their text", {"ask.released", "ask.blocked"} <= actions)
check("encrypted runs: no plaintext in the audit meta", all("vacaciones" not in json.dumps(e) for e in http.get(f"{PORTAL}/api/v1/audit?limit=200", headers=acme).json()))
print(f"\nALL {passed} CHECKS PASSED")
