"""Create schema + RLS policies + append-only audit trigger. Run with the *admin* DB URL:

    python -m app.db.bootstrap
"""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.db.models import TENANT_TABLES, Base

log = logging.getLogger("nexus.bootstrap")

# No bypass clause: the app role can never see another tenant's rows, whatever SQL it runs.
# Cross-tenant work (seeding, demo simulator, schema) uses the owner role, which bypasses RLS natively.
_PRED = "(tenant_id = current_setting('app.tenant_id', true))"


def apply_schema(engine: Engine, app_role: str | None = None) -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name != "postgresql":
        log.warning("Non-PostgreSQL database: RLS not applied (ORM scoping only). Dev/test use only.")
        return
    role = app_role or get_settings().db_app_role
    with engine.begin() as c:
        for t in TENANT_TABLES:
            c.execute(text(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"))
            c.execute(text(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY"))
            c.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {t}"))
            c.execute(text(f"CREATE POLICY tenant_isolation ON {t} USING {_PRED} WITH CHECK {_PRED}"))
        c.execute(text("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY"))
        c.execute(text("ALTER TABLE tenants FORCE ROW LEVEL SECURITY"))
        c.execute(text("DROP POLICY IF EXISTS tenant_isolation ON tenants"))
        c.execute(
            text(
                "CREATE POLICY tenant_isolation ON tenants "
                "USING (id = current_setting('app.tenant_id', true)) WITH CHECK (false)"
            )
        )
        # Login must find a user before any tenant is known. A narrowly-scoped SECURITY DEFINER
        # function exposes exactly one row by exact email — nothing else crosses tenants.
        c.execute(text("DROP FUNCTION IF EXISTS nexus_auth_user(text)"))
        c.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION nexus_auth_user(p_email text)
                RETURNS TABLE (id varchar, tenant_id varchar, email varchar, full_name varchar,
                               password_hash varchar, role varchar, is_active boolean, mfa_enabled boolean)
                LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
                    SELECT u.id, u.tenant_id, u.email, u.full_name, u.password_hash, u.role, u.is_active, u.mfa_enabled
                    FROM users u WHERE u.email = p_email LIMIT 1
                $$
                """
            )
        )
        c.execute(text("REVOKE ALL ON FUNCTION nexus_auth_user(text) FROM PUBLIC"))
        # Append-only audit log: trigger + minimal grants.
        c.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$ LANGUAGE plpgsql
                """
            )
        )
        c.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_mutation ON audit_logs"))
        c.execute(
            text(
                "CREATE TRIGGER audit_logs_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_logs "
                "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable()"
            )
        )
        # The trigger above is statement-level for TRUNCATE; row-level for UPDATE/DELETE:
        c.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_row_mutation ON audit_logs"))
        c.execute(
            text(
                "CREATE TRIGGER audit_logs_no_row_mutation BEFORE UPDATE OR DELETE ON audit_logs "
                "FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()"
            )
        )
        exists = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first()
        if exists:
            c.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            c.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
            c.execute(text(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM "{role}"'))
            c.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
            c.execute(text(f'GRANT EXECUTE ON FUNCTION nexus_auth_user(text) TO "{role}"'))
        else:
            log.warning("Role %s not found: grants skipped (is the app connecting as owner/superuser? RLS would be bypassed)", role)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    engine = create_engine(s.database_admin_url or s.database_url)
    apply_schema(engine)
    log.info("Schema + RLS applied on %s", engine.dialect.name)


if __name__ == "__main__":
    main()
