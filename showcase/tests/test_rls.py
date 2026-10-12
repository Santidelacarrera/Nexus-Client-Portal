"""Garantías de la BASE DE DATOS, con los roles reales de la aplicación (no superusuario, sin BYPASSRLS)."""
import uuid

import asyncpg
import pytest




async def _session(conn, sid: uuid.UUID | None = None) -> uuid.UUID:
    sid = sid or uuid.uuid4()
    await conn.execute("SELECT set_config('app.session_id', $1, false)", str(sid))
    await conn.execute("INSERT INTO visitor_sessions (id, expires_at) VALUES ($1, now() + interval '1 hour')", sid)
    return sid


async def test_roles_are_not_privileged(admin_conn):
    rows = await admin_conn.fetch("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'showcase_%'")
    assert {r["rolname"] for r in rows} == {"showcase_app", "showcase_staff"}
    assert not any(r["rolsuper"] or r["rolbypassrls"] for r in rows)


async def test_rls_enabled_and_forced_on_all_tables(admin_conn):
    rows = await admin_conn.fetch(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r'"
    )
    assert {r["relname"] for r in rows} >= {"visitor_sessions", "consent_records", "contact_messages"}
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)


async def test_public_role_cannot_read_messages(app_dsn):
    conn = await asyncpg.connect(app_dsn)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.fetch("SELECT * FROM contact_messages")
    finally:
        await conn.close()


async def test_session_isolation(app_dsn):
    a, b = await asyncpg.connect(app_dsn), await asyncpg.connect(app_dsn)
    try:
        sa = await _session(a)
        await a.execute("INSERT INTO consent_records (id, session_id, consent_key, granted, policy_version) VALUES (gen_random_uuid(), $1,'consentimiento_ley_21719', true,'v1')", sa)
        await _session(b)  # b opera como OTRA sesión
        assert await b.fetchval("SELECT count(*) FROM consent_records") == 0
        assert await a.fetchval("SELECT count(*) FROM consent_records") == 1
    finally:
        await a.close(); await b.close()


async def test_cannot_act_as_another_session(app_dsn):
    conn = await asyncpg.connect(app_dsn)
    try:
        await _session(conn)
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("INSERT INTO consent_records (id, session_id, consent_key, granted, policy_version) VALUES (gen_random_uuid(), $1,'consentimiento_ley_21719', true,'v1')", uuid.uuid4())
    finally:
        await conn.close()


async def test_consent_is_append_only(app_dsn, admin_conn):
    conn = await asyncpg.connect(app_dsn)
    try:
        sid = await _session(conn)
        await conn.execute("INSERT INTO consent_records (id, session_id, consent_key, granted, policy_version) VALUES (gen_random_uuid(), $1,'consentimiento_ley_21719', true,'v1')", sid)
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("UPDATE consent_records SET policy_version='v2'")
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("DELETE FROM consent_records")
    finally:
        await conn.close()
    with pytest.raises(asyncpg.PostgresError):  # ni siquiera el propietario puede reescribir la evidencia (trigger)
        await admin_conn.execute("UPDATE consent_records SET policy_version='v2'")


async def test_consent_key_is_constrained(app_dsn):
    conn = await asyncpg.connect(app_dsn)
    try:
        sid = await _session(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("INSERT INTO consent_records (id, session_id, consent_key, granted, policy_version) VALUES (gen_random_uuid(), $1,'otra_cosa', true,'v1')", sid)
    finally:
        await conn.close()


async def test_message_without_consent_is_rejected(app_dsn):
    conn = await asyncpg.connect(app_dsn)
    try:
        sid = await _session(conn)
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "INSERT INTO contact_messages (session_id, consent_id, name, email, message) VALUES ($1,$2,'Ana','a@b.co','mensaje de prueba válido')",
                sid, uuid.uuid4(),
            )
    finally:
        await conn.close()


async def test_staff_can_read_and_only_update_status(app_dsn, staff_dsn, visitor, admin_conn):
    from tests.conftest import VALID

    c, csrf = visitor
    assert (await c.post("/api/v1/contacto", json=VALID, headers=csrf)).status_code == 201
    staff = await asyncpg.connect(staff_dsn)
    try:
        rows = await staff.fetch("SELECT id, email FROM contact_messages")
        assert rows
        await staff.execute("UPDATE contact_messages SET status='leido' WHERE id=$1", rows[0]["id"])
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await staff.execute("UPDATE contact_messages SET email='x@y.co' WHERE id=$1", rows[0]["id"])
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await staff.execute("DELETE FROM contact_messages")
    finally:
        await staff.close()
    app = await asyncpg.connect(app_dsn)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute("UPDATE contact_messages SET status='leido'")
    finally:
        await app.close()


async def test_retention_purge(admin_conn, visitor):
    from tests.conftest import VALID

    c, csrf = visitor
    await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    await admin_conn.execute("UPDATE contact_messages SET retain_until = now() - interval '1 day'")
    assert await admin_conn.fetchval("SELECT purge_expired_contact_messages()") >= 1
    assert await admin_conn.fetchval("SELECT count(*) FROM contact_messages") == 0
