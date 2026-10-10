"""Real PostgreSQL RLS test. Runs only when TEST_PG_ADMIN_URL and TEST_PG_APP_URL are set (CI / docker)."""
import os

import pytest
from sqlalchemy import create_engine, text

ADMIN, APP = os.getenv("TEST_PG_ADMIN_URL"), os.getenv("TEST_PG_APP_URL")
pytestmark = pytest.mark.skipif(not (ADMIN and APP), reason="PostgreSQL not configured")


def test_rls_blocks_cross_tenant_reads_and_writes():
    from app.db.bootstrap import apply_schema

    admin = create_engine(ADMIN)
    apply_schema(admin, app_role=create_engine(APP).url.username)
    with admin.begin() as c:
        c.execute(text("DELETE FROM api_findings")) if False else None
        for i in ("t-a", "t-b"):
            c.execute(text("INSERT INTO tenants (id,name,slug,plan,created_at) VALUES (:i,:i,:i,'p',now()) ON CONFLICT DO NOTHING"), {"i": i})
    app = create_engine(APP)
    with app.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id','t-a',true)"))
        c.execute(text("INSERT INTO api_findings (id,tenant_id,category,severity,status,method,endpoint,title,description,evidence,cvss,detected_at,source) VALUES ('f-a','t-a','BOLA','low','open','GET','/','t','d','{}',1,now(),'x') ON CONFLICT DO NOTHING"))
    with app.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id','t-b',true)"))
        assert c.execute(text("SELECT count(*) FROM api_findings WHERE id='f-a'")).scalar() == 0
        with pytest.raises(Exception):  # WITH CHECK forbids writing a foreign tenant's row
            c.execute(text("INSERT INTO api_findings (id,tenant_id,category,severity,status,method,endpoint,title,description,evidence,cvss,detected_at,source) VALUES ('f-x','t-a','BOLA','low','open','GET','/','t','d','{}',1,now(),'x')"))
    with app.begin() as c:  # no tenant set at all → fail closed
        assert c.execute(text("SELECT count(*) FROM api_findings")).scalar() == 0
    with app.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id','t-a',true)"))
        c.execute(text("INSERT INTO audit_logs (tenant_id,ts,action,meta,prev_hash,entry_hash) VALUES ('t-a',now(),'x','{}','0','1')"))
    with pytest.raises(Exception):  # append-only
        with app.begin() as c:
            c.execute(text("SELECT set_config('app.tenant_id','t-a',true)"))
            c.execute(text("DELETE FROM audit_logs"))


def test_app_role_cannot_escape_rls_even_by_setting_flags():
    app = create_engine(APP)
    with app.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls','on',true), set_config('app.tenant_id','t-b',true)"))
        assert c.execute(text("SELECT count(*) FROM api_findings WHERE tenant_id='t-a'")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM tenants WHERE id='t-a'")).scalar() == 0
    with pytest.raises(Exception):  # tenants are not writable by the app role at all
        with app.begin() as c:
            c.execute(text("INSERT INTO tenants (id,name,slug,plan,created_at) VALUES ('evil','e','evil','p',now())"))


def test_login_lookup_function_exposes_one_row_by_exact_email():
    app = create_engine(APP)
    with app.begin() as c:
        rows = c.execute(text("SELECT * FROM nexus_auth_user('nobody@nowhere.example')")).all()
        assert rows == []
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 0
