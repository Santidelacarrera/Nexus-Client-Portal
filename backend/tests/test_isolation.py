import pytest
from sqlalchemy import select

from app.db.models import ApiFinding, RagQuery, Report
from app.db.session import CrossTenantError, TenantContextError, system_session, tenant_session


def test_lists_only_contain_own_tenant(client, acme, helix):
    with system_session() as db:
        helix_ids = {r for r in db.scalars(select(RagQuery.id).where(RagQuery.tenant_id == helix["tenant"]["id"]))}
        helix_findings = {r for r in db.scalars(select(ApiFinding.id).where(ApiFinding.tenant_id == helix["tenant"]["id"]))}
    a_rag = {q["id"] for q in client.get("/api/v1/rag/queries?limit=200", headers=acme["h"]).json()}
    a_find = {f["id"] for f in client.get("/api/v1/security/findings?limit=500", headers=acme["h"]).json()}
    assert a_rag and a_find
    assert not (a_rag & helix_ids) and not (a_find & helix_findings)


def test_direct_object_access_across_tenants_is_404(client, acme, helix):
    with system_session() as db:
        foreign = db.scalars(select(RagQuery.id).where(RagQuery.tenant_id == helix["tenant"]["id"])).first()
    assert client.get(f"/api/v1/rag/queries/{foreign}", headers=acme["h"]).status_code == 404
    assert client.get(f"/api/v1/rag/queries/{foreign}", headers=helix["h"]).status_code == 200


def test_reports_not_downloadable_by_other_tenant(client, acme, helix):
    rid = client.post("/api/v1/reports/generate", headers=helix["h"]).json()["id"]
    assert client.get(f"/api/v1/reports/{rid}/download", headers=acme["h"]).status_code == 404
    assert client.get(f"/api/v1/reports/{rid}/verify", headers=acme["h"]).status_code == 404
    assert rid not in {r["id"] for r in client.get("/api/v1/reports", headers=acme["h"]).json()}


def test_audit_log_is_tenant_scoped(client, acme, helix):
    entries = client.get("/api/v1/audit?limit=500", headers=acme["h"]).json()
    assert entries
    with system_session() as db:
        helix_ids = set(db.scalars(select(ApiFinding.id).where(ApiFinding.tenant_id == helix["tenant"]["id"])))
    assert not any(e["resource"] in helix_ids for e in entries)


def test_orm_blocks_queries_without_tenant_context(client):
    from sqlalchemy.orm import Session

    from app.db.session import get_engine

    s = Session(get_engine(), info={"tenant_id": None, "system": False})
    with pytest.raises(TenantContextError):
        s.scalars(select(ApiFinding)).all()


def test_orm_blocks_cross_tenant_writes(client, acme, helix):
    with tenant_session(acme["tenant"]["id"]) as db:
        db.add(ApiFinding(tenant_id=helix["tenant"]["id"], category="BOLA", severity="low", method="GET", endpoint="/x", title="t", description="d"))
        with pytest.raises(CrossTenantError):
            db.flush()


def test_new_rows_default_to_session_tenant(client, acme):
    with tenant_session(acme["tenant"]["id"]) as db:
        f = ApiFinding(category="BOLA", severity="low", method="GET", endpoint="/auto", title="auto", description="d")
        db.add(f)
        db.flush()
        assert f.tenant_id == acme["tenant"]["id"]
        db.rollback()


def test_session_never_sees_other_tenant_even_by_pk(client, acme, helix):
    with system_session() as db:
        foreign = db.scalars(select(Report.id).where(Report.tenant_id == helix["tenant"]["id"])).first() or db.scalars(select(ApiFinding.id).where(ApiFinding.tenant_id == helix["tenant"]["id"])).first()
    with tenant_session(acme["tenant"]["id"]) as db:
        assert db.scalars(select(ApiFinding).where(ApiFinding.id == foreign)).first() is None
